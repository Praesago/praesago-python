"""Client for the Praesago API (England and Wales property and area data)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from ._version import __version__
from .errors import PraesagoError, error_for

DEFAULT_BASE_URL = "https://praesago.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class Credits:
    """Credit headers from the last keyed response. None when the server did not send them."""

    charged: Optional[int] = None
    remaining: Optional[int] = None


class Praesago:
    """Praesago API client.

    >>> from praesago import Praesago
    >>> client = Praesago()            # reads PRAESAGO_API_KEY
    >>> client.district("E17")["area_name"]
    'Walthamstow'

    Every method returns the ``data`` part of the reply. Errors raise a subclass of
    :class:`praesago.PraesagoError`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("PRAESAGO_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_credits = Credits()

    # ---- district data -------------------------------------------------

    def district(self, district: str, sections: Optional[Iterable[str]] = None) -> dict:
        """Everything held for one postcode district. ``sections`` limits the reply (see :meth:`catalogue`)."""
        params = {"sections": ",".join(sections)} if sections else None
        return self._get(f"/api/agent/v1/district/{_q(district)}", params)

    def context(self, district: str) -> dict:
        """Property market context for a district."""
        return self._get(f"/api/v1/districts/{_q(district)}/context")

    def sectors(self, district: str) -> dict:
        """Sold prices by postcode sector inside a district (a median needs 10 or more sales)."""
        return self._get(f"/api/v1/districts/{_q(district)}/sectors")

    def sold_psf(self, district: str) -> dict:
        """Sold price per square foot (houses)."""
        return self._get(f"/api/v1/districts/{_q(district)}/sold-psf")

    def rental(self, district: str) -> dict:
        """Rental yield and rent by bedroom count, rental demand and Local Housing Allowance rates."""
        return self._get(f"/api/v1/districts/{_q(district)}/rental")

    def price_history(self, district: str, months: Optional[int] = None) -> dict:
        """Monthly HPI averages and yearly ONS medians."""
        return self._get(f"/api/v1/districts/{_q(district)}/price-history", {"months": months})

    def planning(self, district: str, months: Optional[int] = None) -> dict:
        """Planning activity for a district (1 to 24 months, default 12)."""
        return self._get(f"/api/v1/planning/{_q(district)}", {"months": months})

    def listings(
        self,
        district: str,
        channel: Optional[str] = None,
        weeks: Optional[int] = None,
        source: Optional[str] = None,
    ) -> dict:
        """Weekly asking-market statistics. ``channel`` is ``"sale"`` or ``"rent"``."""
        return self._get(
            f"/api/v1/listings/{_q(district)}", {"channel": channel, "weeks": weeks, "source": source}
        )

    # ---- many districts ------------------------------------------------

    def movers(self, channel: Optional[str] = None, metric: Optional[str] = None, limit: Optional[int] = None) -> Any:
        """Districts with the biggest week-over-week change. ``metric`` is ``"price"`` or ``"inventory"``."""
        return self._get("/api/v1/listings/movers", {"channel": channel, "metric": metric, "limit": limit})

    def search(self, q: str, limit: Optional[int] = None) -> Any:
        """Find districts by outcode or place name."""
        return self._get("/api/v1/districts/search", {"q": q, "limit": limit})

    def screen(self, **filters: Any) -> Any:
        """Screen districts, for example ``screen(min_yield_pct=6, max_median_price_gbp=250000, sort_by="yield")``.

        Filters: min/max_median_price_gbp, min/max_asking_rent_pcm, min_sale_listings, min/max_price_cut_pct,
        min/max_yield_pct, region, sort_by (price, rent, listings, price_cut, yield), order (asc, desc), limit.
        """
        return self._get("/api/v1/screen", filters)

    def compare(self, a: str, b: str) -> dict:
        """Compare two postcode districts."""
        return self._get("/api/v1/compare", {"a": a, "b": b})

    def batch(self, districts: Iterable[str]) -> Any:
        """Headline facts for up to 50 districts in one call (1 credit for each district found)."""
        return self._request("POST", "/api/v1/districts/batch", body={"districts": list(districts)})

    # ---- no key needed -------------------------------------------------

    def catalogue(self) -> dict:
        """Sources, licences, periods and coverage. No key needed."""
        return self._get("/api/v1/catalogue")

    def demo(self) -> dict:
        """Real figures for one fixed district. No key needed."""
        return self._get("/api/v1/demo")

    # ---- transport -----------------------------------------------------

    def _get(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Any] = None,
    ) -> Any:
        url = self.base_url + path
        clean = {k: _param(v) for k, v in (params or {}).items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
        headers = {"Accept": "application/json", "User-Agent": f"praesago-python/{__version__}"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self._read_credits(resp.headers)
                    return _unwrap(resp.status, resp.read(), resp.headers)
            except urllib.error.HTTPError as exc:
                self._read_credits(exc.headers)
                raw = exc.read()
                if exc.code in RETRY_STATUSES and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(_retry_delay(exc.headers, attempt))
                    continue
                raise _to_error(exc.code, raw, exc.headers) from None
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    time.sleep(_retry_delay(None, attempt))
                    continue
                raise PraesagoError(f"Network error: {exc.reason}", status=None, code="network") from None

    def _read_credits(self, headers: Any) -> None:
        if headers is None:
            return
        self.last_credits = Credits(
            charged=_int(headers.get("X-Credits-Charged")),
            remaining=_int(headers.get("X-Credits-Remaining")),
        )


def _q(segment: str) -> str:
    return urllib.parse.quote(segment.strip().upper().replace(" ", ""), safe="")


def _param(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _retry_delay(headers: Any, attempt: int) -> float:
    if headers is not None:
        after = headers.get("Retry-After")
        if after:
            try:
                return min(float(after), 30.0)
            except ValueError:
                pass
    return min(0.5 * 2 ** (attempt - 1), 8.0)


def _unwrap(status: int, raw: bytes, headers: Any) -> Any:
    payload = _json(raw)
    if not isinstance(payload, dict):
        raise PraesagoError("The server sent a reply that is not JSON", status=status, code="bad_response")
    if payload.get("success") is False:
        raise _to_error(status, raw, headers)
    return payload.get("data")


def _to_error(status: int, raw: bytes, headers: Any) -> PraesagoError:
    payload = _json(raw)
    if isinstance(payload, dict):
        return error_for(
            status,
            message=payload.get("error") or f"HTTP {status}",
            code=payload.get("code"),
            request_id=payload.get("request_id"),
            details=payload,
            retry_after=_int(headers.get("Retry-After")) if headers is not None else None,
        )
    return error_for(status, message=f"HTTP {status} (reply is not JSON)", code=None)


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
