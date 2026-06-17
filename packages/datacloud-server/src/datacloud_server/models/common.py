"""Shared Pydantic models: unified API response wrapper + query operators."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiResponse[T](BaseModel):
    """Unified API response: {code, success, message, data}."""

    code: int = 200
    success: bool = True
    message: str = "ok"
    data: T | None = None

    model_config = ConfigDict(extra="forbid")


def ok(data: object = None, message: str = "ok") -> ApiResponse[Any]:
    """Shorthand for success response."""
    return ApiResponse(code=200, success=True, message=message, data=data)
