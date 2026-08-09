"""View definition and ViewProperty Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ViewProperty(BaseModel):
    """View property definition (4 fields) — references source object/property."""

    property_name: str = Field(alias="propertyName")
    property_code: str = Field(alias="propertyCode")
    source_object: str = Field(alias="sourceObject")
    source_object_property: str = Field(alias="sourceObjectProperty")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class View(BaseModel):
    """View definition (5 fields)."""

    view_code: str = Field(alias="viewCode")
    view_name: str = Field(alias="viewName")
    description: str | None = Field(default=None, alias="description")
    object_codes: list[str] = Field(default_factory=list, alias="objectCodes")
    properties: list[ViewProperty] = Field(default_factory=list, alias="properties")
    owner_type: str = Field(default="enterprise", alias="ownerType")
    user_code: str | None = Field(default=None, alias="userCode")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    publish_id: str | None = Field(default=None, alias="publishId")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
