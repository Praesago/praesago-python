"""Errors raised by the Praesago client. Branch on ``code`` (stable), not on the message text."""

from __future__ import annotations

from typing import Any, Optional


class PraesagoError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Any = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.request_id = request_id
        self.details = details
        self.retry_after = retry_after

    def __str__(self) -> str:
        extra = ", ".join(
            f"{k}={v}" for k, v in (("status", self.status), ("code", self.code), ("request_id", self.request_id)) if v
        )
        return f"{self.message} ({extra})" if extra else self.message


class AuthenticationError(PraesagoError):
    """401: the key is missing or not valid. Create one at https://praesago.com/settings/api-keys."""


class InsufficientCreditsError(PraesagoError):
    """402: not enough credits. Buy more at https://praesago.com/pricing."""


class NotFoundError(PraesagoError):
    """404: no such postcode district (England and Wales only)."""


class RateLimitError(PraesagoError):
    """429: too many requests. ``retry_after`` gives seconds when the server sends it."""


class BadRequestError(PraesagoError):
    """400: a parameter is not valid."""


class ServerError(PraesagoError):
    """5xx: a fault on the Praesago side. Quote ``request_id`` when you write to support."""


def error_for(status: int, *, message: str, code: Optional[str], **kw: Any) -> PraesagoError:
    if status == 401:
        cls = AuthenticationError
    elif status == 402:
        cls = InsufficientCreditsError
    elif status == 404:
        cls = NotFoundError
    elif status == 429:
        cls = RateLimitError
    elif status == 400:
        cls = BadRequestError
    elif status >= 500:
        cls = ServerError
    else:
        cls = PraesagoError
    return cls(message, status=status, code=code, **kw)
