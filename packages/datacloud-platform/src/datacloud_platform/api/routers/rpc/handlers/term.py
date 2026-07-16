"""RPC handlers for term-related services.

Services: termLibrary, termType, term, termRelation, termName, termKnowledge, domain.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok

from datacloud_knowledge.contracts.term_provider_types import (
    QueryResult,
)

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


def _base(params: dict[str, Any]) -> str:
    """从 params 中提取 base_id，未提供时使用默认值 DEFAULT_BASE_ID。"""
    base_id: object = params.get("base_id", DEFAULT_BASE_ID)
    return str(base_id)


# ── termLibrary ──────────────────────────────────────────────────────────────


def _term_library_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {}
    if params.get("library_code"):
        kwargs["library_code"] = params["library_code"]
    if params.get("library_name"):
        kwargs["library_name"] = params["library_name"]
    return ok(data=platform.list_term_libraries(_base(params), **kwargs))


def _term_library_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_library(
            _base(params), library=params.get("library", {})
        ),
        message="created",
    )


def _term_library_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    lib_id: str = params.get("id", "")
    lib = platform.get_term_library(_base(params), library_id=lib_id)
    if lib is None:
        raise KeyError(f"TermLibrary '{lib_id}' not found")
    return ok(data=lib)


def _term_library_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    lib_id: str = params.get("id", "")
    platform.update_term_library(
        _base(params), library_id=lib_id, updates=params.get("updates", {})
    )
    return ok(data={"libraryId": lib_id})


def _term_library_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_library(_base(params), library_id=params.get("id", ""))
    return ok(message="deleted")


LIBRARY_REGISTRY: dict[str, Any] = {
    "list": _term_library_list,
    "create": _term_library_create,
    "get": _term_library_get,
    "update": _term_library_update,
    "delete": _term_library_delete,
}


# ── termType ─────────────────────────────────────────────────────────────────


def _term_type_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "library_id": params.get("library_id")
        or params.get("libraryId")
        or _base(params),
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 20),
    }
    if params.get("domain_code"):
        kwargs["domain_code"] = params["domain_code"]
    if params.get("type_category") is not None:
        kwargs["type_category"] = params["type_category"]
    if params.get("keyword"):
        kwargs["keyword"] = params["keyword"]
    return ok(data=platform.list_term_types(_base(params), **kwargs))


def _term_type_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_type(
            _base(params), term_type=params.get("term_type", {})
        ),
        message="created",
    )


def _term_type_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    library_id: str = (
        params.get("library_id") or params.get("libraryId") or _base(params)
    )
    code: str = params.get("code", "")
    tt = platform.get_term_type(_base(params), library_id=library_id, type_code=code)
    if tt is None:
        raise KeyError(f"TermType '{code}' not found")
    return ok(data=tt)


def _term_type_get_relations(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """#3 — 术语类型一跳关系 (ADR-006: 直接查 term_relation.term_type_code 列)。"""
    kwargs: dict[str, Any] = {
        "library_id": params.get("library_id")
        or params.get("libraryId")
        or _base(params),
        "type_code": params.get("type_code", ""),
        "direction": params.get("direction", "both"),
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 20),
    }
    if params.get("relation_category"):
        kwargs["relation_category"] = params["relation_category"]
    if params.get("keyword"):
        kwargs["keyword"] = params["keyword"]
    return ok(data=platform.list_term_type_relations(_base(params), **kwargs))


def _term_type_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    library_id: str = (
        params.get("library_id") or params.get("libraryId") or _base(params)
    )
    code: str = params.get("code", "")
    platform.update_term_type(
        _base(params),
        library_id=library_id,
        type_code=code,
        updates=params.get("updates", {}),
    )
    return ok(data={"typeCode": code})


def _term_type_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_type(
        _base(params),
        library_id=params.get("library_id") or params.get("libraryId") or _base(params),
        type_code=params.get("code", ""),
    )
    return ok(message="deleted")


TYPE_REGISTRY: dict[str, Any] = {
    "list": _term_type_list,
    "create": _term_type_create,
    "get": _term_type_get,
    "getRelations": _term_type_get_relations,
    "update": _term_type_update,
    "delete": _term_type_delete,
}


# ── term ─────────────────────────────────────────────────────────────────────


def _term_search(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    search_kwargs: dict[str, Any] = {}
    field_map: dict[str, str] = {
        "datasetIds": "dataset_ids",
        "keyword": "keyword",
        "termName": "term_name",
        "termType": "term_type",
        "queryType": "query_type",
        "parentTermCode": "parent_term_code",
        "labelFilters": "label_filters",
        "labelCondition": "label_condition",
        "termIds": "term_ids",
        "topK": "top_k",
        "offset": "offset",
        "extAttrs": "ext_attrs",
    }
    for camel, snake in field_map.items():
        if snake in params:
            search_kwargs[snake] = params[snake]
        elif camel in params:
            search_kwargs[snake] = params[camel]
    return ok(data=platform.search_terms(_base(params), **search_kwargs))


def _term_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 20),
    }
    # Support both library_id (new) and dataset_id (deprecated alias)
    library_id = params.get("library_id") or params.get("libraryId") or _base(params)
    if library_id:
        kwargs["library_id"] = library_id
    if params.get("term_type"):
        kwargs["term_type"] = params["term_type"]
    if params.get("domain_code"):
        kwargs["domain_code"] = params["domain_code"]
    if params.get("keyword"):
        kwargs["keyword"] = params["keyword"]
    return ok(data=platform.list_terms(_base(params), **kwargs))


def _term_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term(_base(params), term=params.get("term", {})),
        message="created",
    )


def _term_import(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """#7 — 批量导入（5 阶段：预检→去重→类型→术语→关系）。"""
    library_id = params.get("library_id") or params.get("libraryId") or _base(params)
    backfill = params.get("backfill", True)
    return ok(
        data=platform.import_terms(
            _base(params),
            library_id=library_id,
            terms=params.get("terms", []),
            backfill=backfill,
        ),
        message="imported",
    )


def _term_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """#5 — 术语详情。"""
    term_id: str = params.get("id", "")
    library_id = params.get("library_id") or params.get("libraryId") or _base(params)
    term = platform.get_term_detail(
        _base(params),
        library_id=library_id,
        term_id=term_id,
    )
    if term is None:
        raise KeyError(f"Term '{term_id}' not found")
    return ok(data=term)


def _term_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    term_id: str = params.get("id", "")
    library_id = params.get("library_id") or params.get("libraryId") or _base(params)
    platform.update_term(
        _base(params),
        library_id=library_id,
        term_id=term_id,
        updates=params.get("updates", {}),
    )
    return ok(data={"termId": term_id})


def _term_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """#8b — 级联删除（relation + name + knowledge）。"""
    platform.delete_term(_base(params), term_id=params.get("id", ""))
    return ok(message="deleted")


def _term_get_relations(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """#6 — 术语一跳关系。"""
    kwargs: dict[str, Any] = {
        "term_id": params.get("id", ""),
        "direction": params.get("direction", "both"),
        "depth": params.get("depth", 1),
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 20),
    }
    if params.get("relation_category"):
        kwargs["relation_category"] = params["relation_category"]
    if params.get("keyword"):
        kwargs["keyword"] = params["keyword"]
    return ok(data=platform.query_term_relations(_base(params), **kwargs))


def _term_get_knowledge_by_word(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """术语知识图谱查询。

    参数说明:
    - keywords: list[str] - 关键词列表（最多20个）
    - term_ids: list[str] - 术语ID列表（最多20个）
    - searchLevel: str - 关系查询深度，"0" = 仅返回术语本身不含 graph，"1" = 1层关系，"all" = 所有层级（默认 "1"）
    - disambiguation_mode: str - 消歧模式，"auto" = 自动选择top1（默认），"return_all" = 返回所有候选术语
    - max_candidates: int - return_all 模式下每个关键词返回的最大候选数（默认 5）
    - kb_ids: list[str] - 可选，按知识库 ID 过滤
    - relationCategory: str - 可选，按关系类别过滤，"metadata" = ONTOLOGY，"instance" = BUSINESS

    返回格式:
    {
        "root_terms": [
            {
                "term_id": "...",
                "term_name": "...",
                "graph": [...],       # searchLevel=0 时为空列表
                "max_depth": 0
            }
        ],
        "total_terms": 10
    }
    """
    # 参数验证
    keywords = params.get("keywords")
    term_ids = params.get("term_ids")

    # 至少提供一种参数
    if not keywords and not term_ids:
        raise ValueError("One of keywords or term_ids is required")

    # keywords 校验
    if keywords:
        if not isinstance(keywords, list):
            raise ValueError("keywords must be a list")
        if len(keywords) > 20:
            raise ValueError("keywords list exceeds maximum limit of 20")

    # term_ids 校验
    if term_ids:
        if not isinstance(term_ids, list):
            raise ValueError("term_ids must be a list")
        if len(term_ids) > 20:
            raise ValueError("term_ids list exceeds maximum limit of 20")

    search_level = params.get("searchLevel", "1")
    disambiguation_mode = params.get("disambiguation_mode", "auto")
    max_candidates = params.get("max_candidates", 5)
    base_id = _base(params)

    # 获取 ext_attrs 过滤条件
    filter_kb_ids = params.get("kb_ids")

    # 关系类别过滤：metadata → ONTOLOGY, instance → BUSINESS
    _RELATION_CATEGORY_MAP: dict[str, str] = {
        "metadata": "ONTOLOGY",
        "instance": "BUSINESS",
    }
    raw_category = params.get("relationCategory")
    filter_relation_category: str | None = None
    if raw_category:
        if raw_category not in _RELATION_CATEGORY_MAP:
            raise ValueError(
                f"relationCategory must be 'metadata' or 'instance', got '{raw_category}'"
            )
        filter_relation_category = _RELATION_CATEGORY_MAP[raw_category]

    # 解析查询深度: "0" = 不查询关系, "1" = 1层, "all" = 无限制
    if search_level == "0":
        max_level = 0
    elif search_level == "all":
        max_level = 999
    else:
        try:
            max_level = int(search_level)
        except ValueError:
            max_level = 1

    # 验证 disambiguation_mode 参数
    if disambiguation_mode not in ("auto", "return_all"):
        raise ValueError("disambiguation_mode must be 'auto' or 'return_all'")

    # 验证 max_candidates 参数
    try:
        max_candidates = int(max_candidates)
        if max_candidates < 1 or max_candidates > 20:
            raise ValueError("max_candidates must be between 1 and 20")
    except (TypeError, ValueError) as e:
        raise ValueError("max_candidates must be an integer between 1 and 20") from e

    # 批量查询根术语
    root_terms: list[dict[str, Any]] = []
    visited_term_ids: set[str] = set()

    # 处理精准 term_ids 查询
    precise_term_ids: list[str] = []
    if term_ids:
        precise_term_ids.extend(term_ids)

    for tid in precise_term_ids:
        if tid in visited_term_ids:
            continue

        # 直接获取术语详情
        term_detail = platform.get_term_detail(base_id, library_id=base_id, term_id=tid)
        if not term_detail:
            continue

        ext_attrs = (
            term_detail.ext_attrs
            if hasattr(term_detail, "ext_attrs") and term_detail.ext_attrs
            else {}
        )

        # 应用 ext_attrs 过滤
        if filter_kb_ids:
            if not ext_attrs or not isinstance(ext_attrs, dict):
                continue

            term_kb_id = ext_attrs.get("kb_id")
            if str(term_kb_id) not in filter_kb_ids:
                continue

        # 构建根节点
        term_name = term_detail.term_name if hasattr(term_detail, "term_name") else ""
        term_dict = {
            "term_id": tid,
            "term_name": term_name,
            "term_code": (
                term_detail.term_code if hasattr(term_detail, "term_code") else ""
            ),
            "term_type": (
                term_detail.term_type if hasattr(term_detail, "term_type") else ""
            ),
            "attributes": ext_attrs if isinstance(ext_attrs, dict) else {},
            "path": term_name,
            "depth": 0,
            "seg": str(len(root_terms) + 1),
        }

        root_terms.append(term_dict)
        visited_term_ids.add(tid)

    # 处理关键词查询
    if keywords:
        for keyword in keywords:
            # 使用混合检索策略（BM25 + 向量语义）
            search_result: Any = platform.search_terms(
                base_id, keyword=keyword, query_type="mixed", top_k=20
            )

            # 如果设置了过滤条件，检查是否匹配
            if filter_kb_ids:
                items = sorted(
                    [
                        item
                        for item in search_result.items
                        if item.ext_attrs.get("kb_id", "") in filter_kb_ids
                    ],
                    key=lambda x: abs(len(x.term_name) - len(keyword)),
                )
                items_total = len(items)
                search_result = QueryResult(items=items, total=items_total)

            # 兼容 QueryResult dataclass 和 dict 两种返回类型
            result_items: Any
            if hasattr(search_result, "items"):
                result_items = search_result.items
            else:
                result_items = (
                    search_result.get("items", [])
                    if hasattr(search_result, "get")
                    else []
                )

            if result_items:
                # 优先查找精确匹配
                exact_matches = []
                for item in result_items:
                    if hasattr(item, "term_name"):
                        term_name = item.term_name
                    elif hasattr(item, "get"):
                        term_name = item.get("term_name")
                    else:
                        term_name = None

                    if hasattr(item, "term_code"):
                        term_code = item.term_code
                    elif hasattr(item, "get"):
                        term_code = item.get("term_code")
                    else:
                        term_code = None

                    # 不区分大小写的精确匹配
                    if (term_name and term_name.lower() == keyword.lower()) or (
                        term_code and term_code.lower() == keyword.lower()
                    ):
                        exact_matches.append(item)

                # 根据 disambiguation_mode 决定候选术语列表
                candidate_items: list[Any]
                if exact_matches:
                    # 有精确匹配时，根据模式返回精确匹配结果
                    if disambiguation_mode == "return_all":
                        candidate_items = exact_matches[:max_candidates]
                    else:
                        candidate_items = [exact_matches[0]]
                else:
                    # 无精确匹配时，根据模式返回相似度排序结果
                    if disambiguation_mode == "return_all":
                        candidate_items = result_items[:max_candidates]
                    else:
                        candidate_items = [result_items[0]]

                # 处理所有候选术语
                for term_item in candidate_items:
                    # 提取 term_id (兼容 dataclass 和 dict)
                    term_id = (
                        term_item.term_id
                        if hasattr(term_item, "term_id")
                        else term_item.get("term_id")
                    )

                    if term_id not in visited_term_ids:
                        # 获取术语详情以提取 ext_attrs
                        term_detail = platform.get_term_detail(
                            base_id, library_id=base_id, term_id=term_id
                        )

                        ext_attrs = None
                        if term_detail:
                            if hasattr(term_detail, "ext_attrs"):
                                ext_attrs = term_detail.ext_attrs
                            elif hasattr(term_detail, "get"):
                                ext_attrs = term_detail.get("ext_attrs")

                        logger.info(
                            "Term %s (%s) ext_attrs: %s",
                            term_id,
                            term_item.term_name
                            if hasattr(term_item, "term_name")
                            else term_item.get("term_name"),
                            ext_attrs,
                        )

                        # 构建根节点统一结构
                        term_name = (
                            term_item.term_name
                            if hasattr(term_item, "term_name")
                            else term_item.get("term_name", "")
                        )
                        term_dict = {
                            "term_id": term_id,
                            "term_name": term_name,
                            "term_code": (
                                term_item.term_code
                                if hasattr(term_item, "term_code")
                                else term_item.get("term_code", "")
                            ),
                            "term_type": (
                                term_item.term_type
                                if hasattr(term_item, "term_type")
                                else term_item.get("term_type", "")
                            ),
                            "attributes": ext_attrs
                            if ext_attrs and isinstance(ext_attrs, dict)
                            else {},
                            "path": term_name,
                            "depth": 0,
                            "seg": str(len(root_terms) + 1),
                        }

                        root_terms.append(term_dict)
                        visited_term_ids.add(term_id)

    if not root_terms:
        return ok(data={"error": "No term found for keyword"})

    # 为每个 root_term 递归获取关系图谱
    for idx, root_term in enumerate(root_terms, start=1):
        root_seg = str(idx)
        relations = _fetch_relations_recursive(
            platform,
            base_id,
            root_term["term_id"],
            root_term["term_name"],
            root_term["term_name"],
            1,
            max_level,
            root_seg,
            visited_term_ids,
            filter_relation_category,
        )
        root_term["graph"] = relations
        root_term["max_depth"] = max((r["depth"] for r in relations), default=0)

    total_terms = sum(len(rt["graph"]) for rt in root_terms) + len(root_terms)

    return ok(
        data={
            "root_terms": root_terms,
            "total_terms": total_terms,
        }
    )


def _fetch_relations_recursive(
    platform: DatacloudPlatform,
    base_id: str,
    term_id: str,
    term_name: str,
    current_path: str,
    current_level: int,
    max_level: int,
    parent_seg: str,
    visited_terms: set[str],
    relation_category: str | None = None,
) -> list[dict[str, Any]]:
    """通过递归 CTE 一次查询获取多跳关系树，构建 LLM 友好的图结构。"""
    if current_level > max_level:
        return []

    # 一次查询获取完整关系树（含 term 详情 JOIN）
    tree_data = platform.query_term_relations_tree(
        base_id,
        term_id=term_id,
        max_depth=max_level - current_level + 1,
        relation_category=relation_category,
    )
    edges: list[dict[str, Any]] = tree_data.get("data", [])
    if not edges:
        return []

    # Sort by depth for BFS-order processing
    edges.sort(key=lambda e: e.get("depth", 0))

    # term_id → (path, seg, term_name)
    node_info: dict[str, tuple[str, str, str]] = {
        term_id: (current_path, parent_seg, term_name),
    }
    # parent_id → child index counter
    child_counters: dict[str, int] = {}
    result: list[dict[str, Any]] = []

    for edge in edges:
        next_id = edge.get("next_term_id", "")
        if not next_id or next_id in visited_terms or next_id in node_info:
            continue

        source_id = edge.get("source_term_id", "")
        target_id = edge.get("target_term_id", "")
        relation_name = edge.get("relation_name", "")
        depth = edge.get("depth", 1)

        # Determine parent (already in node_info) and child (next_id)
        if source_id == next_id:
            parent_id = target_id
            child_id = source_id
            child_name = edge.get("source_term_name", "")
            arrow = f" <--[{relation_name}]-- "
            child_code = edge.get("source_term_code", "")
            child_type = edge.get("source_term_type", "")
            child_attrs = edge.get("source_ext_attrs", {})
        else:
            parent_id = source_id
            child_id = target_id
            child_name = edge.get("target_term_name", "")
            arrow = f" --[{relation_name}]--> "
            child_code = edge.get("target_term_code", "")
            child_type = edge.get("target_term_type", "")
            child_attrs = edge.get("target_ext_attrs", {})

        if parent_id not in node_info:
            continue  # parent hasn't been processed yet; skip

        parent_path, parent_seg_val, _ = node_info[parent_id]
        child_counters.setdefault(parent_id, 0)
        child_counters[parent_id] += 1

        child_seg = (
            f"{parent_seg_val}.{child_counters[parent_id]}"
            if parent_seg_val != "0"
            else str(child_counters[parent_id])
        )
        child_path = parent_path + arrow + child_name

        node_info[child_id] = (child_path, child_seg, child_name)
        visited_terms.add(child_id)

        result.append(
            {
                "term_id": child_id,
                "term_name": child_name,
                "term_code": child_code,
                "term_type": child_type,
                "attributes": child_attrs if isinstance(child_attrs, dict) else {},
                "path": child_path,
                "depth": current_level + depth - 1,
                "seg": child_seg,
            }
        )

    return result


TERM_REGISTRY: dict[str, Any] = {
    "search": _term_search,
    "list": _term_list,
    "create": _term_create,
    "import": _term_import,
    "get": _term_get,
    "update": _term_update,
    "delete": _term_delete,
    "getRelations": _term_get_relations,
    "getKnowledgeByTermWord": _term_get_knowledge_by_word,
}


# ── termRelation ─────────────────────────────────────────────────────────────


def _term_relation_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 20),
    }
    if params.get("source_term_id"):
        kwargs["source_term_id"] = params["source_term_id"]
    if params.get("target_term_id"):
        kwargs["target_term_id"] = params["target_term_id"]
    if params.get("relation_category"):
        kwargs["relation_category"] = params["relation_category"]
    if params.get("keyword"):
        kwargs["keyword"] = params["keyword"]
    return ok(data=platform.list_term_relations(_base(params), **kwargs))


def _term_relation_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_relation(
            _base(params), relation=params.get("relation", {})
        ),
        message="created",
    )


def _term_relation_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    rel_id: str = params.get("id", "")
    rel = platform.get_term_relation(_base(params), relation_id=rel_id)
    if rel is None:
        raise KeyError(f"TermRelation '{rel_id}' not found")
    return ok(data=rel)


def _term_relation_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    rel_id: str = params.get("id", "")
    platform.update_term_relation(
        _base(params), relation_id=rel_id, updates=params.get("updates", {})
    )
    return ok(data={"relationId": rel_id})


def _term_relation_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_relation(_base(params), relation_id=params.get("id", ""))
    return ok(message="deleted")


RELATION_REGISTRY: dict[str, Any] = {
    "list": _term_relation_list,
    "create": _term_relation_create,
    "get": _term_relation_get,
    "update": _term_relation_update,
    "delete": _term_relation_delete,
}


# ── termName ─────────────────────────────────────────────────────────────────


def _term_name_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {}
    if params.get("term_id"):
        kwargs["term_id"] = params["term_id"]
    if params.get("name_text"):
        kwargs["name_text"] = params["name_text"]
    return ok(data=platform.list_term_names(_base(params), **kwargs))


def _term_name_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_name(_base(params), name=params.get("name", {})),
        message="created",
    )


def _term_name_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    name_id: str = params.get("id", "")
    name = platform.get_term_name(_base(params), name_id=name_id)
    if name is None:
        raise KeyError(f"TermName '{name_id}' not found")
    return ok(data=name)


def _term_name_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    name_id: str = params.get("id", "")
    platform.update_term_name(
        _base(params), name_id=name_id, updates=params.get("updates", {})
    )
    return ok(data={"nameId": name_id})


def _term_name_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_name(_base(params), name_id=params.get("id", ""))
    return ok(message="deleted")


NAME_REGISTRY: dict[str, Any] = {
    "list": _term_name_list,
    "create": _term_name_create,
    "get": _term_name_get,
    "update": _term_name_update,
    "delete": _term_name_delete,
}


# ── termKnowledge ────────────────────────────────────────────────────────────


def _term_knowledge_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {}
    if params.get("term_id"):
        kwargs["term_id"] = params["term_id"]
    if params.get("ext_system"):
        kwargs["ext_system"] = params["ext_system"]
    return ok(data=platform.list_term_knowledges(_base(params), **kwargs))


def _term_knowledge_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_knowledge(
            _base(params), knowledge=params.get("knowledge", {})
        ),
        message="created",
    )


def _term_knowledge_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    knowledge_id: str = params.get("id", "")
    knowledge = platform.get_term_knowledge(_base(params), knowledge_id=knowledge_id)
    if knowledge is None:
        raise KeyError(f"TermKnowledge '{knowledge_id}' not found")
    return ok(data=knowledge)


def _term_knowledge_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    knowledge_id: str = params.get("id", "")
    platform.update_term_knowledge(
        _base(params),
        knowledge_id=knowledge_id,
        updates=params.get("updates", {}),
    )
    return ok(data={"knowledgeId": knowledge_id})


def _term_knowledge_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_knowledge(_base(params), knowledge_id=params.get("id", ""))
    return ok(message="deleted")


KNOWLEDGE_REGISTRY: dict[str, Any] = {
    "list": _term_knowledge_list,
    "create": _term_knowledge_create,
    "get": _term_knowledge_get,
    "update": _term_knowledge_update,
    "delete": _term_knowledge_delete,
}


# ── domain ───────────────────────────────────────────────────────────────────


def _domain_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "library_id": params.get("library_id")
        or params.get("libraryId")
        or _base(params),
    }
    if params.get("parent_id"):
        kwargs["parent_id"] = params["parent_id"]
    return ok(data=platform.list_domains(_base(params), **kwargs))


def _domain_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_domain(_base(params), domain=params.get("domain", {})),
        message="created",
    )


def _domain_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    library_id: str = (
        params.get("library_id") or params.get("libraryId") or _base(params)
    )
    domain_code: str = params.get("code", "")
    domain = platform.get_domain(
        _base(params), library_id=library_id, domain_code=domain_code
    )
    if domain is None:
        raise KeyError(f"Domain '{domain_code}' not found")
    return ok(data=domain)


def _domain_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    library_id: str = (
        params.get("library_id") or params.get("libraryId") or _base(params)
    )
    domain_code: str = params.get("code", "")
    platform.update_domain(
        _base(params),
        library_id=library_id,
        domain_code=domain_code,
        updates=params.get("updates", {}),
    )
    return ok(data={"domainCode": domain_code})


def _domain_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_domain(
        _base(params),
        library_id=params.get("library_id") or params.get("libraryId") or _base(params),
        domain_code=params.get("code", ""),
    )
    return ok(message="deleted")


DOMAIN_REGISTRY: dict[str, Any] = {
    "list": _domain_list,
    "create": _domain_create,
    "get": _domain_get,
    "update": _domain_update,
    "delete": _domain_delete,
}
