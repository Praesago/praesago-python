import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from praesago import (
    AuthenticationError,
    InsufficientCreditsError,
    NotFoundError,
    Praesago,
    PraesagoError,
    RateLimitError,
)


class Stub:
    """A local HTTP server that records requests and replies from a queue."""

    def __init__(self):
        self.requests = []
        self.replies = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                stub.requests.append(
                    {"method": self.command, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}
                )
                status, payload, headers = stub.replies.pop(0) if stub.replies else (200, {"success": True, "data": {}}, {})
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = _serve
            do_POST = _serve

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def reply(self, status, payload, headers=None):
        self.replies.append((status, payload, headers or {}))


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.server.shutdown()


def client(stub, **kw):
    return Praesago("test-key", base_url=stub.url, **kw)


def test_district_path_key_and_unwrap(stub):
    stub.reply(200, {"success": True, "data": {"district": "E17"}}, {"X-Credits-Charged": "3", "X-Credits-Remaining": "497"})
    c = client(stub)
    assert c.district(" e17 ") == {"district": "E17"}
    req = stub.requests[0]
    assert req["path"] == "/api/agent/v1/district/E17"
    assert req["headers"]["x-api-key"] == "test-key"
    assert req["headers"]["user-agent"].startswith("praesago-python/")
    assert c.last_credits.charged == 3 and c.last_credits.remaining == 497


def test_sections_and_none_params_dropped(stub):
    c = client(stub)
    c.district("E17", sections=["property", "crime"])
    c.listings("E17", channel="rent")
    assert stub.requests[0]["path"] == "/api/agent/v1/district/E17?sections=property%2Ccrime"
    assert stub.requests[1]["path"] == "/api/v1/listings/E17?channel=rent"


@pytest.mark.parametrize(
    "call,path",
    [
        (lambda c: c.context("E17"), "/api/v1/districts/E17/context"),
        (lambda c: c.sectors("E17"), "/api/v1/districts/E17/sectors"),
        (lambda c: c.sold_psf("E17"), "/api/v1/districts/E17/sold-psf"),
        (lambda c: c.rental("E17"), "/api/v1/districts/E17/rental"),
        (lambda c: c.price_history("E17", months=24), "/api/v1/districts/E17/price-history?months=24"),
        (lambda c: c.planning("E17", months=6), "/api/v1/planning/E17?months=6"),
        (lambda c: c.movers(metric="inventory"), "/api/v1/listings/movers?metric=inventory"),
        (lambda c: c.search("Walthamstow", limit=5), "/api/v1/districts/search?q=Walthamstow&limit=5"),
        (lambda c: c.screen(min_yield_pct=6, sort_by="yield"), "/api/v1/screen?min_yield_pct=6&sort_by=yield"),
        (lambda c: c.compare("E17", "E18"), "/api/v1/compare?a=E17&b=E18"),
        (lambda c: c.catalogue(), "/api/v1/catalogue"),
        (lambda c: c.demo(), "/api/v1/demo"),
    ],
)
def test_paths(stub, call, path):
    call(client(stub))
    assert stub.requests[0]["path"] == path


def test_batch_posts_json(stub):
    client(stub).batch(["E17", "CF10"])
    req = stub.requests[0]
    assert req["method"] == "POST" and req["path"] == "/api/v1/districts/batch"
    assert json.loads(req["body"]) == {"districts": ["E17", "CF10"]}
    assert req["headers"]["content-type"] == "application/json"


@pytest.mark.parametrize(
    "status,code,cls",
    [(401, "invalid_key", AuthenticationError), (402, "insufficient_credits", InsufficientCreditsError), (404, "not_found", NotFoundError)],
)
def test_errors_map_to_classes(stub, status, code, cls):
    stub.reply(status, {"success": False, "data": None, "error": "nope", "code": code, "request_id": "req_1"})
    with pytest.raises(cls) as exc:
        client(stub).context("ZZ99")
    assert exc.value.code == code and exc.value.request_id == "req_1" and exc.value.status == status


def test_429_retries_then_succeeds(stub):
    stub.reply(429, {"success": False, "error": "slow", "code": "rate_limited"}, {"Retry-After": "0"})
    stub.reply(200, {"success": True, "data": [1]})
    assert client(stub).search("x") == [1]
    assert len(stub.requests) == 2


def test_429_gives_up(stub):
    for _ in range(3):
        stub.reply(429, {"success": False, "error": "slow", "code": "rate_limited"}, {"Retry-After": "0"})
    with pytest.raises(RateLimitError):
        client(stub, max_retries=2).search("x")
    assert len(stub.requests) == 3


def test_non_json_reply(stub):
    stub.reply(404, b"<!DOCTYPE html>")
    with pytest.raises(NotFoundError):
        client(stub).context("E17")


def test_no_key_sends_no_header(stub, monkeypatch):
    monkeypatch.delenv("PRAESAGO_API_KEY", raising=False)
    Praesago(base_url=stub.url).demo()
    assert "x-api-key" not in stub.requests[0]["headers"]


def test_env_key(stub, monkeypatch):
    monkeypatch.setenv("PRAESAGO_API_KEY", "from-env")
    Praesago(base_url=stub.url).demo()
    assert stub.requests[0]["headers"]["x-api-key"] == "from-env"


# ---- live calls: only endpoints that need no key -----------------------


@pytest.mark.live
def test_live_demo_and_catalogue():
    c = Praesago(api_key="")
    assert c.demo()["district"]["district"] == "E17"
    assert "England and Wales" in c.catalogue()["coverage"]


@pytest.mark.live
def test_live_bad_key_is_auth_error():
    with pytest.raises(AuthenticationError) as exc:
        Praesago(api_key="not-a-real-key", max_retries=0).context("E17")
    assert exc.value.code == "invalid_key"


@pytest.mark.live
def test_live_full_district_path_exists():
    # 401 (JSON) proves the route exists; a wrong path gives a 404 web page.
    with pytest.raises(PraesagoError) as exc:
        Praesago(api_key="not-a-real-key", max_retries=0).district("E17")
    assert exc.value.status == 401
