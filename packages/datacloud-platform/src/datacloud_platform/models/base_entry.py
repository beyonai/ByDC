"""OntologyBase CRUD request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OntologyBaseCreate(BaseModel):
    """Create ontology base request.

    ``baseId`` is optional — a snowflake ID is auto-generated when omitted.
    """

    display_name: str = Field(alias="displayName")
    description: str
    base_id: str | None = Field(default=None, alias="baseId")
    owner_type: str = Field(default="personal", alias="ownerType")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    auth_type: str | None = Field(default=None, alias="authType")
    auth_config: dict[str, Any] | None = Field(default=None, alias="authConfig")
    timeout_sec: int = Field(default=30, alias="timeoutSec")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class OntologyBaseUpdate(BaseModel):
    """Update ontology base request — all fields optional.

    ``baseId`` is read-only and silently ignored by the update handler.
    """

    display_name: str | None = Field(default=None, alias="displayName")
    description: str | None = Field(default=None)
    owner_type: str | None = Field(default=None, alias="ownerType")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    auth_type: str | None = Field(default=None, alias="authType")
    auth_config: dict[str, Any] | None = Field(default=None, alias="authConfig")
    timeout_sec: int | None = Field(default=None, alias="timeoutSec")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
