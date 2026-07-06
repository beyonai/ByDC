"""Datasource definition Pydantic models — nested db/doc/api structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DbConnection(BaseModel):
    """Database connection info."""

    db_id: str = Field(alias="dbId")
    db_code: str = Field(alias="dbCode")
    db_type: str = Field(alias="dbType")
    db_params: dict[str, Any] | None = Field(default=None, alias="dbParams")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class DocSource(BaseModel):
    """Document source info."""

    doc_id: str = Field(alias="docId")
    doc_path: str = Field(alias="docPath")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ApiSource(BaseModel):
    """API source info."""

    api_id: str = Field(alias="apiId")
    url: str = Field(alias="url")
    method: str | None = None
    header: dict[str, Any] | None = None
    body: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Datasource(BaseModel):
    """Datasource definition — nested db/doc/api (NOT flattened)."""

    db: list[DbConnection] = Field(default_factory=list)
    doc: list[DocSource] = Field(default_factory=list)
    api: list[ApiSource] = Field(default_factory=list)
    owner_type: str = Field(default="enterprise", alias="ownerType")
    user_code: str | None = Field(default=None, alias="userCode")

    model_config = ConfigDict(extra="allow")
