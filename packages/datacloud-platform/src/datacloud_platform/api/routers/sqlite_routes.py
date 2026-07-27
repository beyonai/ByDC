"""REST endpoint for executing a SQL statement against a SQLite file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from datacloud_platform.execution.sqlite_executor import (
    SqliteExecutionError,
    execute_sqlite_statement,
)
from datacloud_platform.models.common import ApiResponse, ok

router = APIRouter(tags=["SQLite"])


class SqliteExecuteRequest(BaseModel):
    """Request for executing one SQL statement against an existing SQLite file."""

    sql: str = Field(min_length=1)
    sqlite_path: Path = Field(alias="sqlitePath")


@router.post("/sqlite/execute", response_model=ApiResponse[dict[str, Any]])
async def execute_sqlite(
    body: SqliteExecuteRequest,
) -> ApiResponse[dict[str, Any]]:
    """Execute a single SQL statement without blocking the event loop."""
    try:
        result = await anyio.to_thread.run_sync(
            execute_sqlite_statement,
            body.sql,
            body.sqlite_path,
        )
    except SqliteExecutionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ok(data=result)
