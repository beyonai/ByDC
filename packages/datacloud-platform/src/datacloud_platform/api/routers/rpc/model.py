"""Pydantic models for RPC request/response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RpcRequest(BaseModel):
    """Generic RPC request body."""

    params: dict[str, Any] = Field(default_factory=dict)


class RpcResponse(BaseModel):
    """Generic RPC response body — mirrors the project's ok() shape."""

    code: int = 0
    message: str = "ok"
    data: Any = None
