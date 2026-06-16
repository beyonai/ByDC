"""Pydantic v2 request/response schemas for ontology service REST API.

All responses: {code: 200, success: true, message: "ok", data: ...}
Request schemas use camelCase aliases to match the JSON API.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ══════════════════════════════════════════════════
# Unified response wrapper
# ══════════════════════════════════════════════════


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


# ══════════════════════════════════════════════════
# Field definition
# ══════════════════════════════════════════════════


class FieldDef(BaseModel):
    """Field definition within an object."""

    field_code: str = Field(alias="fieldCode")
    field_name: str = Field(alias="fieldName")
    field_type: str = Field(alias="fieldType")
    is_primary_key: bool = Field(default=False, alias="isPrimaryKey")
    required: bool = False
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# ══════════════════════════════════════════════════
# Action definition
# ══════════════════════════════════════════════════


class ActionDef(BaseModel):
    """Action definition within an object."""

    action_code: str = Field(alias="actionCode")
    action_name: str = Field(default="", alias="actionName")
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


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


# ══════════════════════════════════════════════════
# Object schemas
# ══════════════════════════════════════════════════


class ObjectCreate(BaseModel):
    """Create object request."""

    object_code: str = Field(alias="objectCode")
    object_name: str = Field(alias="objectName")
    fields: list[FieldDef] = Field(default_factory=list)
    actions: list[ActionDef] = Field(default_factory=list)
    description: str = ""
    source_type: str = Field(default="DB", alias="sourceType")
    table_name: str = Field(default="", alias="tableName")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ObjectDef(ObjectCreate):
    """Object definition (extends Create with optional extra fields — same shape)."""


# ══════════════════════════════════════════════════
# View schema
# ══════════════════════════════════════════════════


class ViewCreate(BaseModel):
    """Create view request."""

    view_code: str = Field(alias="viewCode")
    view_name: str = Field(alias="viewName")
    object_codes: list[str] = Field(default_factory=list, alias="objectCodes")
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


ViewDef = ViewCreate  # alias for API symmetry


# ══════════════════════════════════════════════════
# Relation schema
# ══════════════════════════════════════════════════


class RelationCreate(BaseModel):
    """Create relation request."""

    relation_code: str = Field(alias="relationCode")
    relation_name: str = Field(alias="relationName")
    source_class: str = Field(default="", alias="sourceClass")
    target_class: str = Field(default="", alias="targetClass")
    relation_type: str = Field(default="", alias="relationType")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


RelationDef = RelationCreate  # alias for API symmetry


# ══════════════════════════════════════════════════
# Datasource schema
# ══════════════════════════════════════════════════


class DatasourceCreate(BaseModel):
    """Create datasource request."""

    db_id: str = Field(alias="dbId")
    db_name: str = Field(alias="dbName")
    db_type: str = Field(default="", alias="dbType")
    host: str = ""
    port: int = 5432
    database: str = ""
    schema_name: str = Field(default="", alias="schema")
    username: str = ""
    password: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
