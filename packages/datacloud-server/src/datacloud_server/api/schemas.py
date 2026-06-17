"""Pydantic v2 request/response schemas for ontology service REST API.

Domain entity models are in datacloud_server.models — this module keeps API-level
schemas (OntologyBase CRUD, auth, etc.) and re-exports domain models for convenience.

All responses: {code: 200, success: true, message: "ok", data: ...}
Request schemas use camelCase aliases to match the JSON API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from datacloud_server.models.common import ApiResponse, ok  # noqa: F401
from datacloud_server.models.datasource import Datasource  # noqa: F401
from datacloud_server.models.object_type import ObjectType  # noqa: F401
from datacloud_server.models.relation import Relation  # noqa: F401
from datacloud_server.models.view import View  # noqa: F401

# ══════════════════════════════════════════════════
# OntologyBase schemas
# ══════════════════════════════════════════════════


class OntologyBaseCreate(BaseModel):
    """Create ontology base request."""

    base_id: str = Field(alias="baseId")
    display_name: str = Field(alias="displayName")
    owner_type: str = Field(default="personal", alias="ownerType")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    auth_type: str | None = Field(default=None, alias="authType")
    auth_config: dict[str, Any] | None = Field(default=None, alias="authConfig")
    timeout_sec: int = Field(default=30, alias="timeoutSec")
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class OntologyBaseResponse(BaseModel):
    """Ontology base response."""

    base_id: str = Field(alias="baseId")
    display_name: str = Field(alias="displayName")
    description: str = ""
    source_type: str = Field(alias="sourceType")
    owner_type: str = Field(alias="ownerType")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    auth_type: str | None = Field(default=None, alias="authType")
    timeout_sec: int = Field(default=30, alias="timeoutSec")
    created_at: str = Field(default="", alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
