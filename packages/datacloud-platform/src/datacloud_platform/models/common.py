"""Shared Pydantic models: unified API response wrapper + query operators."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse[T](BaseModel):
    """Unified API response: {code, success, message, data, ...extra}."""

    code: int = 200
    success: bool = True
    message: str = "ok"
    data: T | None = None

    model_config = ConfigDict(extra="allow")


def ok(
    data: object = None, message: str = "ok", code: int = 200, **extra: Any
) -> ApiResponse[Any]:
    """Shorthand for unified API response.

    ``code`` defaults to 200 (success).  Error handlers pass explicit codes
    (e.g. 400, 404, 500) to signal error responses in the same envelope.

    Extra kwargs (e.g. ``totalCount``) become top-level fields in the response.
    """
    return ApiResponse(code=code, success=True, message=message, data=data, **extra)


def fail(
    message: str, code: int = 500, data: object = None, **extra: Any
) -> ApiResponse[Any]:
    """Build a unified unsuccessful response while preserving the error message."""
    return ApiResponse(code=code, success=False, message=message, data=data, **extra)
