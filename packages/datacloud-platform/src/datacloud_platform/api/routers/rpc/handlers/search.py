"""RPC handlers for 'search' and 'graph' services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


# ── Search handlers ──────────────────────────────────────────────────────────
#
# NOTE: platform.search_ontology() and platform.search_instances() accept
# camelCase parameter names (e.g. "sceneIds", "queryType") directly, matching
# the original REST endpoint conventions.  No snake_case mapping is performed
# here because the platform layer is the canonical consumer of these keys.


def _search_ontology(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.search_ontology(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            scene_ids=params.get("sceneIds", ["-1"]),
            keyword=params.get("keyword", ""),
            query_type=params.get("queryType", "vector"),
            search_scope=params.get("searchScope", "all"),
            metadata_type=params.get("metadataType"),
            object_code=params.get("objectCode"),
            view_code=params.get("viewCode"),
            property_code=params.get("propertyCode"),
            result_per_type=params.get("resultPerType", 5),
            top_k=params.get("topK", 20),
        )
    )


def _search_scene(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    scene_ids: list[str] = params.get("scene_ids", [])
    return ok(
        data=platform.search_ontology(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            scene_ids=scene_ids,
            keyword=params.get("keyword", ""),
            query_type=params.get("queryType", "vector"),
            search_scope=params.get("searchScope", "all"),
            metadata_type=params.get("metadataType"),
            object_code=params.get("objectCode"),
            view_code=params.get("viewCode"),
            property_code=params.get("propertyCode"),
            result_per_type=params.get("resultPerType", 5),
            top_k=params.get("topK", 20),
        )
    )


def _search_instances(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.search_instances(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            object_code=params.get("objectCode", ""),
            select=params.get("select"),
            where=params.get("where"),
        )
    )


async def _search_object_instances_unstructured(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """非结构化对象实例检索 RPC handler。

    sentence 模式:
        {"query": "自然语言句子", "object_code": "by_opportunity", ...}

    word_batch 模式:
        {"queries": ["词1", "词2"], "object_code": null, ...}
    """
    result = await platform.search_object_instances_unstructured(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_code=params.get("object_code"),
        query=params.get("query"),
        queries=params.get("queries"),
        top_k=params.get("top_k", 20),
        enable_chunk_recall=params.get("enable_chunk_recall", True),
        kb_configs=params.get("kb_configs"),
    )
    # Serialize results dict directly — caller gets {keyword: [hit, ...]}
    return ok(data=result.results)


REGISTRY: dict[str, Any] = {
    "searchOntology": _search_ontology,
    "searchScene": _search_scene,
    "searchInstances": _search_instances,
    "searchObjectInstancesUnstructured": _search_object_instances_unstructured,
}


# ── Graph handlers ───────────────────────────────────────────────────────────


def _graph_query(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.graph_query(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            scene_id=params.get("scene_id", ""),
            object_code=params.get("objectCodes", params.get("objectCode", [])),
            match_by=params.get("matchBy", "name"),
            values=params.get("values"),
            step=params.get("depth", params.get("step", 1)),
        )
    )


def _graph_shortest_path(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.graph_path(
            base_id=params.get("base_id", DEFAULT_BASE_ID),
            scene_id=params.get("scene_id", ""),
            match_by=params.get("matchBy", "name"),
            start_node=params.get("sourceObjectCode", ""),
            end_node=params.get("targetObjectCode", ""),
            direction=params.get("direction", "forward"),
        )
    )


GRAPH_REGISTRY: dict[str, Any] = {
    "query": _graph_query,
    "shortestPath": _graph_shortest_path,
}
