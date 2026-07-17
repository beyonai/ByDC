"""RPC handlers for term-related services.

Services: termLibrary, termType, term, termRelation, termName, termKnowledge, domain.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok

from datacloud_platform.models.graph_query import (
    _parse_query_profile,
    _resolve_graph_query_options,
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
    """术语知识图谱查询 — 委托给 query_knowledge_graph 编排方法。

    入参:
    - keywords: list[str] | None
    - term_ids: list[str] | None
    - kb_ids: list[str] | None
    - queryProfile: str (默认 "graph_fast")
    - searchLevel: 可选覆盖深度
    - disambiguation_mode: str (默认 "auto")
    - max_candidates: int | None (1-20)
    """
    query_profile = _parse_query_profile(params)
    options = _resolve_graph_query_options(params, query_profile)
    base_id = _base(params)

    keywords: list[str] | None = params.get("keywords")
    term_ids: list[str] | None = params.get("term_ids")
    kb_ids_raw: list[str] | None = params.get("kb_ids")
    kb_ids = set(kb_ids_raw) if kb_ids_raw else None
    _raw_mode = str(params.get("disambiguation_mode", "auto"))
    if _raw_mode not in ("auto", "return_all"):
        raise ValueError("disambiguation_mode must be 'auto' or 'return_all'")
    disambiguation_mode: str = _raw_mode

    if params.get("returnTermOrKnowledge") == "knowledge":
        raise ValueError("returnTermOrKnowledge=knowledge mode is no longer supported")

    if not keywords and not term_ids:
        raise ValueError("One of keywords or term_ids is required")

    # Parse relationCategory (metadata → ONTOLOGY, instance → BUSINESS)
    _rel_cat_map: dict[str, str] = {"metadata": "ONTOLOGY", "instance": "BUSINESS"}
    relation_category: str | None = None
    if params.get("relationCategory") is not None:
        raw_cat = str(params.get("relationCategory"))
        relation_category = _rel_cat_map.get(raw_cat, raw_cat)

    # Validate keywords
    if keywords:
        if not isinstance(keywords, list):
            raise ValueError("keywords must be a list")
        if len(keywords) > 20:
            raise ValueError("keywords list exceeds maximum limit of 20")

    # Validate term_ids
    if term_ids:
        if not isinstance(term_ids, list):
            raise ValueError("term_ids must be a list")
        if len(term_ids) > 20:
            raise ValueError("term_ids list exceeds maximum limit of 20")

    result = platform.query_knowledge_graph(
        base_id,
        options=options,
        keywords=keywords,
        term_ids=term_ids,
        kb_ids=kb_ids,
        disambiguation_mode=disambiguation_mode,
        relation_category=relation_category,
    )
    return ok(data=result)


def _term_get_connection_network(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    """getTermConnectionNetwork — 术语连接网络图谱计算。

    计算 source_terms → target_terms 之间的连接路径、桥接节点、
    知识引用和连接摘要。Backend 做图算法（解析 + BFS 路径搜索 + 评分），
    Agent 做推理和表达。
    """
    base_id = _base(params)

    source_terms: list[str] = params.get("source_terms", [])
    if not source_terms:
        raise ValueError("source_terms is required (at least 1)")

    target_terms: list[str] = params.get("target_terms", [])
    if not target_terms:
        raise ValueError("target_terms is required (at least 1)")

    max_depth: int = int(params.get("max_depth", 3))
    if not 1 <= max_depth <= 4:
        raise ValueError("max_depth must be 1..4")

    max_paths: int = int(params.get("max_paths", 12))
    if not 1 <= max_paths <= 50:
        raise ValueError("max_paths must be 1..50")

    direction: str = str(params.get("direction", "both"))
    if direction not in ("out", "in", "both"):
        raise ValueError("direction must be out/in/both")

    kb_ids: list[str] | None = params.get("kb_ids")
    relation_names: list[str] | None = params.get("relation_names")
    bridge_terms: list[str] | None = params.get("bridge_terms")
    include_knowledge_refs: bool = bool(params.get("include_knowledge_refs", True))
    include_debug: bool = bool(params.get("include_debug", False))

    # Parse relationCategory (metadata → ONTOLOGY, instance → BUSINESS)
    _rel_cat_map: dict[str, str] = {"metadata": "ONTOLOGY", "instance": "BUSINESS"}
    relation_category: str | None = None
    if params.get("relationCategory") is not None:
        raw_cat = str(params.get("relationCategory"))
        relation_category = _rel_cat_map.get(raw_cat, raw_cat)

    result = platform.get_term_connection_network(
        base_id,
        source_terms=source_terms,
        target_terms=target_terms,
        kb_ids=kb_ids,
        max_depth=max_depth,
        max_paths=max_paths,
        direction=direction,
        relation_names=relation_names,
        bridge_terms=bridge_terms,
        relation_category=relation_category,
        include_knowledge_refs=include_knowledge_refs,
        include_debug=include_debug,
    )
    return ok(data=result)


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
    "getTermConnectionNetwork": _term_get_connection_network,
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
