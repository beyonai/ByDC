"""RPC handlers for 'search' and 'graph' services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID

logger = logging.getLogger(__name__)

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
        {"query": "自然语言句子", "object_codes": ["by_opportunity"], ...}

    word_batch 模式:
        {"queries": ["词1", "词2"], "object_codes": null, ...}
    """
    logger.warning(
        "searchObjectInstancesUnstructured ENTRY: object_codes=%s query=%r queries=%r top_k=%s chunk=%s",
        params.get("object_codes"),
        params.get("query"),
        params.get("queries"),
        params.get("top_k", 5),
        params.get("enable_chunk_recall", True),
    )
    result = await platform.search_object_instances_unstructured(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_codes=params.get("object_codes"),
        query=params.get("query"),
        queries=params.get("queries"),
        top_k=params.get("top_k", 5),
        enable_chunk_recall=params.get("enable_chunk_recall", True),
    )
    # Serialize results dict directly — caller gets {keyword: [hit, ...]}
    return ok(data=result.results)


async def _search_object_instances_unstructured_paged(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """非结构化对象实例检索 — 分页候选推荐 RPC handler（纯 sentence 模式）。

    语义说明：
    (a) 候选池内 RRF 语义、非全量精确分页：fetch_top 只放大候选池，
        分页是"融合后排名列表"上的切片，不是全量快照精确分页。
    (b) 跨页顺序不保证稳定（RRF 固有属性）：第 2 页候选池比第 1 页长，
        同一 term 的 rank 会变、可能出现跨页重复条目。
    (c) 纯 sentence 模式：屏蔽 queries（word_batch）与 enable_chunk_recall
        （路2 固定关闭——表单候选推荐场景字段为结构化关键字、每键防抖
        触发延迟敏感，路1 为主、保延迟）；需要 KB 召回时走旧接口。
    (d) 忽略客户端传入的 top_k（pageSize 取代其语义），否则分页数学被破坏。

    入参：base_id / object_codes / query 与旧接口一致；page（默认 1）与
    pageSize（默认 5）钳制到 >=1，offset 只在融合结果之上切片（严禁下推
    到 search_terms_batch 的 offset 参数，RRF rank 会错位）。
    返回信封：{"results": {query: [hit, ...]}, "pagination": {...}}，
    has_more 为单 bool（offset+limit 之后是否还有候选）。
    """
    page = max(1, int(params.get("page", 1)))
    page_size = max(1, int(params.get("pageSize", 5)))
    offset = (page - 1) * page_size
    limit = page_size
    fetch_top = offset + limit + 1  # +1 为 has_more 哨兵

    logger.warning(
        "searchObjectInstancesUnstructuredPaged ENTRY: object_codes=%s query=%r "
        "page=%s pageSize=%s fetch_top=%s",
        params.get("object_codes"),
        params.get("query"),
        page,
        page_size,
        fetch_top,
    )

    result = await platform.search_object_instances_unstructured(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_codes=params.get("object_codes"),
        query=params.get("query"),
        queries=None,
        top_k=fetch_top,
        enable_chunk_recall=False,
    )

    results: dict[str, list[Any]] = {}
    has_more = False
    for keyword, hits in result.results.items():
        results[keyword] = list(hits[offset : offset + limit])
        if len(hits) > offset + limit:
            has_more = True

    return ok(
        data={
            "results": results,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "has_more": has_more,
            },
        }
    )


async def _enumerate_object_instances(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """枚举带度数的对象实例 RPC handler（枚举型接口，非检索）。

    入参（camelCase 由 RPC 层约定透传）：
        object_codes:    list[str] | None — 对象类型范围（与 kb 范围 AND）
        kb_resource_ids: list[str] | None — 知识库资源范围
        filters:         list[dict] | None — 条件数组，**原样透传不解析**
        page:            int，默认 1，钳制 >=1
        pageSize:        int，默认 20，钳制 >=1

    语义钉死：
    (a) filters 只透传——不解析/不校验 filter type/params；非法 type/params
        由 knowledge 层 validate 抛 ValueError → 既有 _EXCEPTION_MAP
        （ValueError → 400 invalid_params）自动映射，handler 无需自定义。
    (b) 范围全空（object_codes 与 kb_resource_ids 均为空）→ 空结果
        （items=[], total=0），即使 filters 有值（filters 不代替范围）。
    (c) 返回信封 {items, total, page, pageSize}；items 为
        ObjectInstanceListItem（9 字段含 out_degree/in_degree）。
    """
    page = max(1, int(params.get("page", 1)))
    page_size = max(1, int(params.get("pageSize", 20)))

    logger.warning(
        "enumerateObjectInstances ENTRY: object_codes=%s kb_resource_ids=%s "
        "filters=%r page=%s pageSize=%s",
        params.get("object_codes"),
        params.get("kb_resource_ids"),
        params.get("filters"),
        page,
        page_size,
    )

    result = platform.enumerate_object_instances(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_codes=params.get("object_codes"),
        kb_resource_ids=params.get("kb_resource_ids"),
        filters=params.get("filters"),
        page=page,
        page_size=page_size,
    )
    return ok(
        data={
            "items": result.items,
            "total": result.total,
            "page": page,
            "pageSize": page_size,
        }
    )


REGISTRY: dict[str, Any] = {
    "searchOntology": _search_ontology,
    "searchScene": _search_scene,
    "searchInstances": _search_instances,
    "searchObjectInstancesUnstructured": _search_object_instances_unstructured,
    "searchObjectInstancesUnstructuredPaged": (
        _search_object_instances_unstructured_paged
    ),
    "enumerateObjectInstances": _enumerate_object_instances,
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
