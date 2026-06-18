"""ObjectType definition and ObjectTypeSummary Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from datacloud_platform.models.action import Action  # noqa: TC001
from datacloud_platform.models.property import Property  # noqa: TC001


class ObjectType(BaseModel):
    """Object type definition (13 API fields — properties and actions embedded)."""

    object_id: str | None = Field(default=None, alias="objectId")
    object_code: str = Field(alias="objectCode")
    object_name: str = Field(alias="objectName")
    object_source: str | None = Field(default=None, alias="objectSource")
    object_desc: str | None = Field(default=None, alias="objectDesc")
    concept_type: str | None = Field(default=None, alias="conceptType")
    object_type: str | None = Field(default=None, alias="objectType")
    domain_type: str | None = Field(default=None, alias="domainType")
    scene_id: str | None = Field(default=None, alias="sceneId")
    source_config: dict[str, Any] | None = Field(default=None, alias="sourceConfig")
    table_name: str | None = Field(default=None, alias="tableName")
    properties: list[Property] = Field(default_factory=list, alias="properties")
    actions: list[Action] = Field(default_factory=list, alias="actions")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ObjectTypeSummary(BaseModel):
    """Object type summary for listObjects response (7 fields)."""

    object_code: str = Field(alias="objectCode")
    object_name: str = Field(alias="objectName")
    object_source: str | None = Field(default=None, alias="objectSource")
    object_desc: str | None = Field(default=None, alias="objectDesc")
    concept_type: str | None = Field(default=None, alias="conceptType")
    field_count: int = Field(default=0, alias="fieldCount")
    action_count: int = Field(default=0, alias="actionCount")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
