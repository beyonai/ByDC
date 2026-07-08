"""RPC handlers for term-related services.

Services: termLibrary, termType, term, termRelation, termName, termKnowledge, domain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def _base(platform: DatacloudPlatform) -> str:
    return platform._default_base_id()


# ── termLibrary ──────────────────────────────────────────────────────────────


def _term_library_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {}
    if params.get("library_code"):
        kwargs["library_code"] = params["library_code"]
    if params.get("library_name"):
        kwargs["library_name"] = params["library_name"]
    return ok(data=platform.list_term_libraries(_base(platform), **kwargs))


def _term_library_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_library(_base(platform), library=params["library"]),
        message="created",
    )


def _term_library_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    lib_id: str = params["id"]
    lib = platform.get_term_library(_base(platform), library_id=lib_id)
    if lib is None:
        raise KeyError(f"TermLibrary '{lib_id}' not found")
    return ok(data=lib)


def _term_library_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    lib_id: str = params["id"]
    platform.update_term_library(
        _base(platform), library_id=lib_id, updates=params.get("updates", {})
    )
    return ok(data={"libraryId": lib_id})


def _term_library_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_library(_base(platform), library_id=params["id"])
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
    kwargs: dict[str, Any] = {}
    if params.get("type_category") is not None:
        kwargs["type_category"] = params["type_category"]
    return ok(data=platform.list_term_types(_base(platform), **kwargs))


def _term_type_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_type(_base(platform), term_type=params["term_type"]),
        message="created",
    )


def _term_type_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    tt = platform.get_term_type(_base(platform), type_code=code)
    if tt is None:
        raise KeyError(f"TermType '{code}' not found")
    return ok(data=tt)


def _term_type_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    code: str = params["code"]
    platform.update_term_type(
        _base(platform), type_code=code, updates=params.get("updates", {})
    )
    return ok(data={"typeCode": code})


def _term_type_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_type(_base(platform), type_code=params["code"])
    return ok(message="deleted")


TYPE_REGISTRY: dict[str, Any] = {
    "list": _term_type_list,
    "create": _term_type_create,
    "get": _term_type_get,
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
    }
    for camel, snake in field_map.items():
        if camel in params:
            search_kwargs[snake] = params[camel]
    return ok(data=platform.search_terms(_base(platform), **search_kwargs))


def _term_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "page_index": params.get("page_index", 1),
        "page_size": params.get("page_size", 50),
    }
    if params.get("dataset_id"):
        kwargs["dataset_id"] = params["dataset_id"]
    if params.get("term_type"):
        kwargs["term_type"] = params["term_type"]
    return ok(data=platform.list_terms(_base(platform), **kwargs))


def _term_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term(_base(platform), term=params["term"]),
        message="created",
    )


def _term_import(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.import_terms(
            _base(platform),
            dataset_id=params.get("libraryId", ""),
            terms=params.get("terms", []),
        ),
        message="imported",
    )


def _term_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    term_id: str = params["id"]
    term = platform.get_term_detail(
        _base(platform),
        dataset_id=params.get("dataset_id", ""),
        term_id=term_id,
    )
    if term is None:
        raise KeyError(f"Term '{term_id}' not found")
    return ok(data=term)


def _term_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    term_id: str = params["id"]
    platform.update_term(
        _base(platform),
        dataset_id=params.get("datasetId", ""),
        term_id=term_id,
        updates=params.get("updates", {}),
    )
    return ok(data={"termId": term_id})


def _term_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term(_base(platform), term_id=params["id"])
    return ok(message="deleted")


def _term_get_relations(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {
        "term_id": params["id"],
        "direction": params.get("direction", "both"),
        "depth": params.get("depth", 1),
    }
    if params.get("relation_category"):
        kwargs["relation_category"] = params["relation_category"]
    return ok(data=platform.query_term_relations(_base(platform), **kwargs))


TERM_REGISTRY: dict[str, Any] = {
    "search": _term_search,
    "list": _term_list,
    "create": _term_create,
    "import": _term_import,
    "get": _term_get,
    "update": _term_update,
    "delete": _term_delete,
    "getRelations": _term_get_relations,
}


# ── termRelation ─────────────────────────────────────────────────────────────


def _term_relation_list(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    kwargs: dict[str, Any] = {}
    if params.get("source_term_id"):
        kwargs["source_term_id"] = params["source_term_id"]
    if params.get("target_term_id"):
        kwargs["target_term_id"] = params["target_term_id"]
    if params.get("relation_category"):
        kwargs["relation_category"] = params["relation_category"]
    return ok(data=platform.list_term_relations(_base(platform), **kwargs))


def _term_relation_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_relation(
            _base(platform), relation=params["relation"]
        ),
        message="created",
    )


def _term_relation_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    rel_id: str = params["id"]
    rel = platform.get_term_relation(_base(platform), relation_id=rel_id)
    if rel is None:
        raise KeyError(f"TermRelation '{rel_id}' not found")
    return ok(data=rel)


def _term_relation_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    rel_id: str = params["id"]
    platform.update_term_relation(
        _base(platform), relation_id=rel_id, updates=params.get("updates", {})
    )
    return ok(data={"relationId": rel_id})


def _term_relation_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_relation(_base(platform), relation_id=params["id"])
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
    return ok(data=platform.list_term_names(_base(platform), **kwargs))


def _term_name_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_name(_base(platform), name=params["name"]),
        message="created",
    )


def _term_name_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    name_id: str = params["id"]
    name = platform.get_term_name(_base(platform), name_id=name_id)
    if name is None:
        raise KeyError(f"TermName '{name_id}' not found")
    return ok(data=name)


def _term_name_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    name_id: str = params["id"]
    platform.update_term_name(
        _base(platform), name_id=name_id, updates=params.get("updates", {})
    )
    return ok(data={"nameId": name_id})


def _term_name_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_name(_base(platform), name_id=params["id"])
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
    return ok(data=platform.list_term_knowledges(_base(platform), **kwargs))


def _term_knowledge_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_term_knowledge(
            _base(platform), knowledge=params["knowledge"]
        ),
        message="created",
    )


def _term_knowledge_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    knowledge_id: str = params["id"]
    knowledge = platform.get_term_knowledge(_base(platform), knowledge_id=knowledge_id)
    if knowledge is None:
        raise KeyError(f"TermKnowledge '{knowledge_id}' not found")
    return ok(data=knowledge)


def _term_knowledge_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    knowledge_id: str = params["id"]
    platform.update_term_knowledge(
        _base(platform),
        knowledge_id=knowledge_id,
        updates=params.get("updates", {}),
    )
    return ok(data={"knowledgeId": knowledge_id})


def _term_knowledge_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_term_knowledge(_base(platform), knowledge_id=params["id"])
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
    kwargs: dict[str, Any] = {}
    if params.get("parent_id"):
        kwargs["parent_id"] = params["parent_id"]
    return ok(data=platform.list_domains(_base(platform), **kwargs))


def _domain_create(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.create_domain(_base(platform), domain=params["domain"]),
        message="created",
    )


def _domain_get(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    domain_id: str = params["id"]
    domain = platform.get_domain(_base(platform), domain_id=domain_id)
    if domain is None:
        raise KeyError(f"Domain '{domain_id}' not found")
    return ok(data=domain)


def _domain_update(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    domain_id: str = params["id"]
    platform.update_domain(
        _base(platform), domain_id=domain_id, updates=params.get("updates", {})
    )
    return ok(data={"domainId": domain_id})


def _domain_delete(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    platform.delete_domain(_base(platform), domain_id=params["id"])
    return ok(message="deleted")


def _domain_list_term_types(
    platform: DatacloudPlatform, params: dict[str, Any], _req: Request
) -> Any:
    return ok(
        data=platform.list_domain_term_types(_base(platform), domain_id=params["id"])
    )


DOMAIN_REGISTRY: dict[str, Any] = {
    "list": _domain_list,
    "create": _domain_create,
    "get": _domain_get,
    "update": _domain_update,
    "delete": _domain_delete,
    "listTermTypes": _domain_list_term_types,
}
