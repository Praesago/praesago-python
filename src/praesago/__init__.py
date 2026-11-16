"""Praesago: England and Wales property and area data for code and AI agents."""

from ._version import __version__
from .client import Credits, Praesago
from .errors import (
    AuthenticationError,
    BadRequestError,
    InsufficientCreditsError,
    NotFoundError,
    PraesagoError,
    RateLimitError,
    ServerError,
)

__all__ = [
    "Praesago",
    "Credits",
    "PraesagoError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "NotFoundError",
    "RateLimitError",
    "BadRequestError",
    "ServerError",
    "__version__",
]
