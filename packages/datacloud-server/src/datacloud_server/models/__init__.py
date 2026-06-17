"""Shared domain model layer — Pydantic v2 entities matching API docs.

All fields use camelCase via Field(alias=...) for JSON serialization.
Internal Python names are snake_case.
"""

from datacloud_server.models.action import Action, ActionParam
from datacloud_server.models.common import ApiResponse, ok
from datacloud_server.models.datasource import ApiSource, Datasource, DbConnection, DocSource
from datacloud_server.models.object_type import ObjectType, ObjectTypeSummary
from datacloud_server.models.ontology import OntologySummary
from datacloud_server.models.property import Property, TermMeta
from datacloud_server.models.relation import Relation
from datacloud_server.models.scene import Scene
from datacloud_server.models.search import (
    InstanceHit,
    MetadataHit,
    ReferencedByProperty,
    SearchRequest,
    SearchResult,
    SearchTotalCount,
)
from datacloud_server.models.view import View, ViewProperty

__all__ = [
    "Action",
    "ActionParam",
    "ApiResponse",
    "ApiSource",
    "Datasource",
    "DbConnection",
    "DocSource",
    "InstanceHit",
    "MetadataHit",
    "ObjectType",
    "ObjectTypeSummary",
    "OntologySummary",
    "Property",
    "ReferencedByProperty",
    "Relation",
    "Scene",
    "SearchRequest",
    "SearchResult",
    "SearchTotalCount",
    "TermMeta",
    "View",
    "ViewProperty",
    "ok",
]
