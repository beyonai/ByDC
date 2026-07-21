"""Shared domain model layer — Pydantic v2 entities + Port layer types.

All Pydantic fields use camelCase via Field(alias=...) for JSON serialization.
Internal Python names are snake_case.
Port layer types (ObjectSummary, EmbeddingHit, etc.) are in shared.py.
"""

from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.base_entry import (
    OntologyBaseCreate,
    OntologyBaseUpdate,
)
from datacloud_platform.models.common import ApiResponse, ok
from datacloud_platform.models.datasource import (
    ApiSource,
    Datasource,
    DbConnection,
    DocSource,
)
from datacloud_platform.models.object_type import ObjectType, ObjectTypeSummary
from datacloud_platform.models.graph_query import (
    GRAPH_QUERY_PROFILE_DEFAULTS,
    GraphQueryOptions,
    GraphQueryProfile,
    _parse_query_profile,
    _resolve_graph_query_options,
)
from datacloud_platform.models.ontology import OntologySummary
from datacloud_platform.models.property import Property, TermMeta
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.term_network import (
    DEFAULT_RELATION_NAMES,
    HUB_THRESHOLD,
    MAX_EDGES,
    ConnectionSummary,
    Edge,
    Gap,
    KnowledgeRef,
    Path,
    PathEdge,
    PathNode,
    ResolvedTerm,
    RELATION_WEIGHTS,
)
from datacloud_platform.models.scene import (
    Scene,
    SceneCreate,
    SceneMembersRequest,
    SceneUpdate,
)
from datacloud_platform.models.search import (
    InstanceHit,
    MetadataHit,
    ReferencedByProperty,
    SearchRequest,
    SearchResult,
    SearchTotalCount,
)
from datacloud_platform.models.shared import (
    DimensionProperty,
    EmbeddingHit,
    MatchCandidate,
    MatchResult,
    ObjectInstanceHit,
    ObjectSummary,
    ParsedOwlContent,
    ReferenceProperty,
    RelationSummary,
    ScoreUpdateRecord,
    StoredFile,
    ViewSummary,
)
from datacloud_platform.models.view import View, ViewProperty

__all__ = [
    "Action",
    "ActionParam",
    "ApiResponse",
    "ApiSource",
    "ConnectionSummary",
    "Datasource",
    "DbConnection",
    "DEFAULT_RELATION_NAMES",
    "DimensionProperty",
    "DocSource",
    "Edge",
    "EmbeddingHit",
    "Gap",
    "HUB_THRESHOLD",
    "KnowledgeRef",
    "InstanceHit",
    "MatchCandidate",
    "MatchResult",
    "MAX_EDGES",
    "MetadataHit",
    "ObjectInstanceHit",
    "ObjectSummary",
    "ObjectType",
    "ObjectTypeSummary",
    "OntologyBaseCreate",
    "OntologyBaseUpdate",
    "GRAPH_QUERY_PROFILE_DEFAULTS",
    "GraphQueryOptions",
    "GraphQueryProfile",
    "_parse_query_profile",
    "_resolve_graph_query_options",
    "OntologySummary",
    "ParsedOwlContent",
    "Path",
    "PathEdge",
    "PathNode",
    "Property",
    "ReferenceProperty",
    "ReferencedByProperty",
    "Relation",
    "RELATION_WEIGHTS",
    "RelationSummary",
    "ResolvedTerm",
    "Scene",
    "SceneCreate",
    "SceneMembersRequest",
    "SceneUpdate",
    "ScoreUpdateRecord",
    "SearchRequest",
    "SearchResult",
    "SearchTotalCount",
    "StoredFile",
    "TermMeta",
    "View",
    "ViewProperty",
    "ViewSummary",
    "ok",
]
