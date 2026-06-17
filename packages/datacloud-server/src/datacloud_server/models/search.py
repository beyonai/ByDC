"""Search models: SearchRequest, MetadataHit, InstanceHit, SearchResult."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """Ontology search request (10 fields)."""

    scene_id: str = Field(alias="sceneId")
    keyword: str = Field(alias="keyword")
    query_type: str = Field(default="vector", alias="queryType")
    search_scope: str = Field(default="all", alias="searchScope")
    object_code: list[str] = Field(default_factory=list, alias="objectCode")
    view_code: list[str] = Field(default_factory=list, alias="viewCode")
    property_code: list[str] = Field(default_factory=list, alias="propertyCode")
    result_per_type: int = Field(default=5, alias="resultPerType")
    page_size: int = Field(default=20, alias="pageSize")
    page_token: str | None = Field(default=None, alias="pageToken")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class MetadataHit(BaseModel):
    """Metadata search hit — union of all resultType variants.

    Uses extra="allow" for resultType-specific additional fields:
    - object: objectCode, objectName, objectDesc, objectSource
    - view: viewCode, viewName, description
    - action: actionCode, actionName, actionDesc, belongObjectCode
    All resultTypes share: sceneId, resultType, matchedField, score.
    """

    scene_id: str = Field(alias="sceneId")
    result_type: str = Field(alias="resultType")
    matched_field: str = Field(alias="matchedField")
    score: float = Field(alias="score")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ReferencedByProperty(BaseModel):
    """Property that references this instance (4 fields)."""

    object_code: str = Field(alias="objectCode")
    object_name: str = Field(alias="objectName")
    property_code: str = Field(alias="propertyCode")
    property_name: str = Field(alias="propertyName")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class InstanceHit(BaseModel):
    """Instance search hit (10 fields)."""

    scene_id: str = Field(alias="sceneId")
    object_code: str = Field(alias="objectCode")
    object_name: str = Field(alias="objectName")
    primary_key: int = Field(alias="primaryKey")
    matched_property: str = Field(alias="matchedProperty")
    matched_value: str = Field(alias="matchedValue")
    is_enum_type: bool = Field(alias="isEnumType")
    referenced_by_properties: list[ReferencedByProperty] = Field(
        default_factory=list, alias="referencedByProperties"
    )
    score: float = Field(alias="score")
    properties: dict[str, Any] = Field(default_factory=dict, alias="properties")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SearchTotalCount(BaseModel):
    """Total counts for metadata and instance results."""

    metadata: int = 0
    instances: int = 0


class SearchResult(BaseModel):
    """Search response (4 fields)."""

    metadata: list[MetadataHit] = Field(default_factory=list)
    instances: list[InstanceHit] = Field(default_factory=list)
    total_count: SearchTotalCount = Field(default_factory=SearchTotalCount, alias="totalCount")
    next_page_token: str | None = Field(default=None, alias="nextPageToken")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
