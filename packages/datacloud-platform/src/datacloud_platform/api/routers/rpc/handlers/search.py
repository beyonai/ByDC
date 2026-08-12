"""RPC handlers for 'search' and 'graph' services."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.mixins.object_instance_discovery import (
    invalidate_vocabulary_cache,
)

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


async def _enumerate_object_instances(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """枚举带度数的对象实例 RPC handler（枚举型接口，非检索）。

    入参（camelCase 由 RPC 层约定透传）：
        object_codes:    list[str] | None — 对象类型范围（与 kb 范围 AND）
        kb_resource_ids: list[str] | None — 知识库资源范围
        filters:         list[dict] | None — 条件数组，**原样透传不解析**
        sort:            dict | None — 排序规格，**原样透传不解析**
        page:            int，默认 1，钳制 >=1
        pageSize:        int，默认 20，钳制 >=1

    语义钉死：
    (a) filters/sort 只透传——不解析/不校验 filter type/params 与 sort by/params；
        非法 type/params/by 由 knowledge 层 validate 抛 ValueError → 既有
        _EXCEPTION_MAP（ValueError → 400 invalid_params）自动映射，handler
        无需自定义。
    (b) 范围全空（object_codes 与 kb_resource_ids 均为空）→ 空结果
        （items=[], total=0），即使 filters 有值（filters 不代替范围）。
    (c) 返回信封 {items, total, page, pageSize}；items 为
        ObjectInstanceListItem（9 字段含 out_degree/in_degree）。
    """
    page = max(1, int(params.get("page", 1)))
    page_size = max(1, int(params.get("pageSize", 20)))

    logger.warning(
        "enumerateObjectInstances ENTRY: object_codes=%s kb_resource_ids=%s "
        "filters=%r sort=%r page=%s pageSize=%s",
        params.get("object_codes"),
        params.get("kb_resource_ids"),
        params.get("filters"),
        params.get("sort"),
        page,
        page_size,
    )

    result = platform.enumerate_object_instances(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        object_codes=params.get("object_codes"),
        kb_resource_ids=params.get("kb_resource_ids"),
        filters=params.get("filters"),
        sort=params.get("sort"),
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


async def _discover_object_instances_unstructured(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """非结构化对象实例发现 RPC handler。

    入参（snake_case，沿用 searchObjectInstancesUnstructured 约定）：
        base_id:      str，默认 DEFAULT_BASE_ID
        instance_id:  str，必填（输入实例 term_id，空 → 400）
        object_codes: list[str]，必填且非空（空/缺失 → 400）

    会话 ID 由全局请求上下文提供（server middleware 注入 InvocationContext），
    不依赖 X-Session-Id 请求头，缺失时登记条目的 sessionId 为空串。
    错误语义由 router._EXCEPTION_MAP 统一映射：KeyError → 404、ValueError → 400、
    NotImplementedError → 501、PermissionError → 403、其他 → 500。
    """
    result = await platform.discover_object_instances_unstructured(
        base_id=params.get("base_id", DEFAULT_BASE_ID),
        instance_id=params.get("instance_id", ""),
        object_codes=params.get("object_codes") or [],
    )
    return ok(data={"items": result.items})


async def _delete_object_instances(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """删除对象实例 RPC handler。

    入参（camelCase，与 enumerateObjectInstances 一致）：
        base_id:          str，默认 DEFAULT_BASE_ID
        objectCodes:      list[str]，**必填且非空**；缺失/为空/含任一空串或
                          纯空白串 → 400 invalid_params（与 discover 的 not all
                          校验一致，空白条目不静默过滤）
        deleteObjectType: bool，默认 False——True 时连本体对象定义一并删除

    删除链路（探索文档 §4.3）：
        1. 实例枚举（enumerate_object_instances 循环分页，诚实 total 终止；
           排除 term_type_code='object' 的对象术语行——对象术语行由
           deleteObjectType=True 的 delete_object/delete_scope 负责）
        2. 共现反向引用清理（remove_term_co_occurrence_partners）
        3. delete_term 级联（term_relation 双向 / term_name / term_knowledge / term）
        4. 词表孤儿清理（delete_orphan_vocabulary_words，孤儿判定兜底）
        5. 词典缓存失效（invalidate_vocabulary_cache）
        6. object file：远程 BE 无删除接口，本接口仅删知识侧，
           文件由 BE 生命周期管理（探索文档 §4.3 步骤 6 结论）
        7. deleteObjectType=True：delete_object_from_all_scenes（清场景引用 +
           EntityStore 幂等删除 + 对象术语行 delete_scope + sync hook）

    幂等语义（探索文档 §4.4）：不存在的 object code → 枚举为空 → deleted=0
    成功；delete_object_from_all_scenes 后端幂等（文件缺失静默）。
    响应：ok(data={"deleted", "deletedObjectTypes", "items": [{object_code,
    term_id, term_name}, ...]})。
    """
    object_codes = params.get("objectCodes") or params.get("object_codes") or []
    normalized = [str(c).strip() for c in object_codes]
    if not normalized or not all(normalized):
        raise ValueError("objectCodes 必须为非空字符串列表，且不允许空串")
    delete_object_type = bool(params.get("deleteObjectType", False))
    base_id = params.get("base_id", DEFAULT_BASE_ID)

    # 1. 实例枚举：循环分页（total 诚实终止）
    instances: list[Any] = []
    page = 1
    page_size = 200
    while True:
        page_result = platform.enumerate_object_instances(
            base_id=base_id,
            object_codes=normalized,
            kb_resource_ids=None,
            page=page,
            page_size=page_size,
        )
        for item in page_result.items:
            # 排除对象术语行（term_type_code='object'，其删除归 deleteObjectType 链路）
            if item.object_code == "object":
                continue
            instances.append(item)
        if page * page_size >= page_result.total:
            break
        page += 1

    # 2+3. 批量删除（单事务级联：共现反向引用/词候选收集/term_name/
    #       term_relation/term_knowledge/term；to_thread 避免阻塞事件循环）
    deleted = 0
    deleted_items: list[dict[str, Any]] = []
    orphan_word_candidates: set[str] = set()
    if instances:
        term_ids = [item.instance_id for item in instances]
        candidates = await asyncio.to_thread(
            platform.delete_terms_batch, base_id, term_ids=term_ids
        )
        orphan_word_candidates.update(candidates)
        deleted = len(term_ids)
        deleted_items = [
            {
                "object_code": item.object_code,
                "term_id": item.instance_id,
                "term_name": item.instance_name,
            }
            for item in instances
        ]

    # 4. 词表孤儿清理：孤儿判定兜底，共享词不误删
    if orphan_word_candidates:
        await asyncio.to_thread(
            platform.delete_orphan_vocabulary_words,
            base_id,
            words=sorted(orphan_word_candidates),
        )

    # 5. 词典缓存失效（飞轮实时）
    invalidate_vocabulary_cache()

    # 7. deleteObjectType=True：对象类型删除（含场景引用清理，O2）
    deleted_object_types = 0
    if delete_object_type:
        for code in normalized:
            platform.delete_object_from_all_scenes(base_id, code)
            deleted_object_types += 1

    return ok(
        data={
            "deleted": deleted,
            "deletedObjectTypes": deleted_object_types,
            "items": deleted_items,
        }
    )


REGISTRY: dict[str, Any] = {
    "searchOntology": _search_ontology,
    "searchScene": _search_scene,
    "searchInstances": _search_instances,
    "searchObjectInstancesUnstructured": _search_object_instances_unstructured,
    "enumerateObjectInstances": _enumerate_object_instances,
    "discoverObjectInstancesUnstructured": _discover_object_instances_unstructured,
    "deleteObjectInstances": _delete_object_instances,
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
