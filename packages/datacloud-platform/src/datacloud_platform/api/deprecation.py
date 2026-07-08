"""Middleware to add deprecation headers to legacy RESTful routes."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Deprecated path prefixes, sorted by length descending to avoid
# short-prefix false matches (e.g. /api/v1/terms must not match /api/v1/term-types/xxx).
_DEPRECATED_PREFIXES = sorted(
    (
        "/api/v1/ontologyBases",
        "/api/v1/ontology-manager",
        "/api/v1/term-libraries",
        "/api/v1/term-types",
        "/api/v1/terms",
        "/api/v1/term-relations",
        "/api/v1/term-names",
        "/api/v1/term-knowledges",
        "/api/v1/datacloud/terms",
        "/api/v1/domains",
        "/api/v1/query",
        "/api/v1/skills",
    ),
    key=len,
    reverse=True,
)

_RPC_PREFIX = "/api/v1/rpc"
DEPRECATION_DATE = "2026-07-08"
SUNSET_DATE = "2027-01-08"


def _is_deprecated(path: str) -> bool:
    """Check if a request path belongs to a legacy RESTful route.

    Ensures full path-segment matching: ``/api/v1/terms`` matches
    ``/api/v1/terms/xxx`` but NOT ``/api/v1/terms-custom``.
    """
    for prefix in _DEPRECATED_PREFIXES:
        if path.startswith(prefix):
            remainder = path[len(prefix) :]
            if not remainder or remainder.startswith("/"):
                return True
    return False


class DeprecationMiddleware(BaseHTTPMiddleware):
    """Add Deprecation + Sunset headers to legacy RESTful API responses."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:  # noqa: ANN401
        response: Response = await call_next(request)
        path = request.url.path

        if path.startswith(_RPC_PREFIX):
            return response

        if _is_deprecated(path):
            response.headers["Deprecation"] = DEPRECATION_DATE
            response.headers["Sunset"] = SUNSET_DATE
            response.headers["Link"] = '</api/v1/rpc>; rel="alternate"; title="RPC API"'

        return response
