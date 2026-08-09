"""Relation definition Pydantic model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Relation(BaseModel):
    """Relation definition (17 fields)."""

    object_relation_id: str | None = Field(default=None, alias="objectRelationId")
    relation_code: str = Field(alias="relationCode")
    relation_name: str | None = Field(default=None, alias="relationName")
    relation_scene_type: str | None = Field(default=None, alias="relationSceneType")
    relation_cardinality: str | None = Field(default=None, alias="relationCardinality")
    relation_desc: str | None = Field(default=None, alias="relationDesc")
    source_object_code: str = Field(alias="sourceObjectCode")
    source_object_name: str | None = Field(default=None, alias="sourceObjectName")
    target_object_code: str = Field(alias="targetObjectCode")
    target_object_name: str | None = Field(default=None, alias="targetObjectName")
    src_meta_id: str | None = Field(default=None, alias="srcMetaId")
    src_column_id: str | None = Field(default=None, alias="srcColumnId")
    target_meta_id: str | None = Field(default=None, alias="targetMetaId")
    target_column_id: str | None = Field(default=None, alias="targetColumnId")
    attribute: dict[str, Any] | None = Field(default=None, alias="attribute")
    sort_no: int = Field(default=0, alias="sortNo")
    status: int = Field(default=0, alias="status")
    owner_type: str = Field(default="enterprise", alias="ownerType")
    user_code: str | None = Field(default=None, alias="userCode")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    publish_id: str | None = Field(default=None, alias="publishId")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
