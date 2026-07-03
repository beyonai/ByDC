"""Term CRUD + Domain routes (factory pattern).

Terms are global (not per-base), so URLs omit the ontologyBases prefix.
All endpoints delegate to platform.term_*() methods via ``_base()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query

from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def create_term_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for Term / TermType / TermLibrary / TermRelation /
    TermName / TermKnowledge / Domain CRUD.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1``.
    """
    router = APIRouter(prefix="/api/v1")

    def _base() -> str:
        return platform._default_base_id()

    # ══════════════════════════════════════════════════
    # TermLibrary CRUD (5 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/term-libraries", tags=["Term"])
    def list_term_libraries(
        library_code: str | None = Query(default=None),
        library_name: str | None = Query(default=None),
    ) -> Any:
        """List term libraries with optional filters."""
        try:
            kwargs: dict[str, Any] = {}
            if library_code is not None:
                kwargs["library_code"] = library_code
            if library_name is not None:
                kwargs["library_name"] = library_name
            return ok(data=platform.list_term_libraries(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/term-libraries", tags=["Term"])
    def create_term_library(body: dict[str, Any]) -> Any:
        """Create a term library."""
        try:
            return ok(
                data=platform.create_term_library(_base(), library=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/term-libraries/{id}", tags=["Term"])
    def get_term_library(id: str) -> Any:
        """Get a term library by ID."""
        try:
            lib = platform.get_term_library(_base(), library_id=id)
            if lib is None:
                raise HTTPException(
                    status_code=404, detail=f"TermLibrary '{id}' not found"
                )
            return ok(data=lib)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/term-libraries/{id}", tags=["Term"])
    def update_term_library(id: str, body: dict[str, Any]) -> Any:
        """Update a term library."""
        try:
            platform.update_term_library(_base(), library_id=id, updates=body)
            return ok(data={"libraryId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/term-libraries/{id}", tags=["Term"])
    def delete_term_library(id: str) -> Any:
        """Delete a term library."""
        try:
            platform.delete_term_library(_base(), library_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # TermType CRUD (5 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/term-types", tags=["Term"])
    def list_term_types(
        type_category: int | None = Query(default=None),
    ) -> Any:
        """List term types with optional category filter."""
        try:
            kwargs: dict[str, Any] = {}
            if type_category is not None:
                kwargs["type_category"] = type_category
            return ok(data=platform.list_term_types(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/term-types", tags=["Term"])
    def create_term_type(body: dict[str, Any]) -> Any:
        """Create a term type."""
        try:
            return ok(
                data=platform.create_term_type(_base(), term_type=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/term-types/{code}", tags=["Term"])
    def get_term_type(code: str) -> Any:
        """Get a term type by code."""
        try:
            tt = platform.get_term_type(_base(), type_code=code)
            if tt is None:
                raise HTTPException(
                    status_code=404, detail=f"TermType '{code}' not found"
                )
            return ok(data=tt)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/term-types/{code}", tags=["Term"])
    def update_term_type(code: str, body: dict[str, Any]) -> Any:
        """Update a term type."""
        try:
            platform.update_term_type(_base(), type_code=code, updates=body)
            return ok(data={"typeCode": code})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/term-types/{code}", tags=["Term"])
    def delete_term_type(code: str) -> Any:
        """Delete a term type."""
        try:
            platform.delete_term_type(_base(), type_code=code)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Term CRUD (8 endpoints)
    # ══════════════════════════════════════════════════

    @router.post("/terms/search", tags=["Term"])
    def search_terms(body: dict[str, Any]) -> Any:
        """Multi-strategy term search (exact/BM25/vector/RRF).

        Body params: dataset_ids, keyword, term_name, term_type,
        query_type, parent_term_code, label_filters, label_condition,
        term_ids, top_k, offset.
        """
        try:
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
                if camel in body:
                    search_kwargs[snake] = body[camel]
            return ok(data=platform.search_terms(_base(), **search_kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/terms", tags=["Term"])
    def list_terms(
        dataset_id: str | None = Query(default=None),
        term_type: str | None = Query(default=None),
        page_index: int = Query(default=1),
        page_size: int = Query(default=50),
    ) -> Any:
        """Paginated list of terms."""
        try:
            kwargs: dict[str, Any] = {"page_index": page_index, "page_size": page_size}
            if dataset_id is not None:
                kwargs["dataset_id"] = dataset_id
            if term_type is not None:
                kwargs["term_type"] = term_type
            return ok(data=platform.list_terms(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/terms", tags=["Term"])
    def create_term(body: dict[str, Any]) -> Any:
        """Create a single term."""
        try:
            return ok(
                data=platform.create_term(_base(), term=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/terms/import", tags=["Term"])
    def import_terms(body: dict[str, Any]) -> Any:
        """Batch import terms. Body: {libraryId, terms: [...]}."""
        try:
            return ok(
                data=platform.import_terms(
                    _base(),
                    dataset_id=body.get("libraryId", ""),
                    terms=body.get("terms", []),
                ),
                message="imported",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/terms/{id}", tags=["Term"])
    def get_term_detail(
        id: str,
        dataset_id: str = Query(default=""),
    ) -> Any:
        """Get a single term's complete detail."""
        try:
            term = platform.get_term_detail(_base(), dataset_id=dataset_id, term_id=id)
            if term is None:
                raise HTTPException(status_code=404, detail=f"Term '{id}' not found")
            return ok(data=term)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/terms/{id}", tags=["Term"])
    def update_term(id: str, body: dict[str, Any]) -> Any:
        """Update a term (partial update). Body includes datasetId."""
        try:
            platform.update_term(
                _base(),
                dataset_id=body.get("datasetId", ""),
                term_id=id,
                updates=body,
            )
            return ok(data={"termId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/terms/{id}", tags=["Term"])
    def delete_term(id: str) -> Any:
        """Delete a term."""
        try:
            platform.delete_term(_base(), term_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/terms/{id}/relations", tags=["Term"])
    def query_term_relations(
        id: str,
        relation_category: str | None = Query(default=None),
        direction: str = Query(default="both"),
        depth: int = Query(default=1),
    ) -> Any:
        """Query a term's related terms (N-hop relations)."""
        try:
            kwargs: dict[str, Any] = {
                "term_id": id,
                "direction": direction,
                "depth": depth,
            }
            if relation_category is not None:
                kwargs["relation_category"] = relation_category
            return ok(data=platform.query_term_relations(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # TermRelation CRUD (5 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/term-relations", tags=["Term"])
    def list_term_relations(
        source_term_id: str | None = Query(default=None),
        target_term_id: str | None = Query(default=None),
        relation_category: str | None = Query(default=None),
    ) -> Any:
        """List term relations with optional filters."""
        try:
            kwargs: dict[str, Any] = {}
            if source_term_id is not None:
                kwargs["source_term_id"] = source_term_id
            if target_term_id is not None:
                kwargs["target_term_id"] = target_term_id
            if relation_category is not None:
                kwargs["relation_category"] = relation_category
            return ok(data=platform.list_term_relations(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/term-relations", tags=["Term"])
    def create_term_relation(body: dict[str, Any]) -> Any:
        """Create a term relation."""
        try:
            return ok(
                data=platform.create_term_relation(_base(), relation=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/term-relations/{id}", tags=["Term"])
    def get_term_relation(id: str) -> Any:
        """Get a term relation by ID."""
        try:
            rel = platform.get_term_relation(_base(), relation_id=id)
            if rel is None:
                raise HTTPException(
                    status_code=404, detail=f"TermRelation '{id}' not found"
                )
            return ok(data=rel)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/term-relations/{id}", tags=["Term"])
    def update_term_relation(id: str, body: dict[str, Any]) -> Any:
        """Update a term relation."""
        try:
            platform.update_term_relation(_base(), relation_id=id, updates=body)
            return ok(data={"relationId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/term-relations/{id}", tags=["Term"])
    def delete_term_relation(id: str) -> Any:
        """Delete a term relation."""
        try:
            platform.delete_term_relation(_base(), relation_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # TermName CRUD (5 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/term-names", tags=["Term"])
    def list_term_names(
        term_id: str | None = Query(default=None),
        name_text: str | None = Query(default=None),
    ) -> Any:
        """List term names with optional filters."""
        try:
            kwargs: dict[str, Any] = {}
            if term_id is not None:
                kwargs["term_id"] = term_id
            if name_text is not None:
                kwargs["name_text"] = name_text
            return ok(data=platform.list_term_names(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/term-names", tags=["Term"])
    def create_term_name(body: dict[str, Any]) -> Any:
        """Create a term name."""
        try:
            return ok(
                data=platform.create_term_name(_base(), name=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/term-names/{id}", tags=["Term"])
    def get_term_name(id: str) -> Any:
        """Get a term name by ID."""
        try:
            name = platform.get_term_name(_base(), name_id=id)
            if name is None:
                raise HTTPException(
                    status_code=404, detail=f"TermName '{id}' not found"
                )
            return ok(data=name)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/term-names/{id}", tags=["Term"])
    def update_term_name(id: str, body: dict[str, Any]) -> Any:
        """Update a term name."""
        try:
            platform.update_term_name(_base(), name_id=id, updates=body)
            return ok(data={"nameId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/term-names/{id}", tags=["Term"])
    def delete_term_name(id: str) -> Any:
        """Delete a term name."""
        try:
            platform.delete_term_name(_base(), name_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # TermKnowledge CRUD (5 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/term-knowledges", tags=["Term"])
    def list_term_knowledges(
        term_id: str | None = Query(default=None),
        ext_system: str | None = Query(default=None),
    ) -> Any:
        """List term knowledges with optional filters."""
        try:
            kwargs: dict[str, Any] = {}
            if term_id is not None:
                kwargs["term_id"] = term_id
            if ext_system is not None:
                kwargs["ext_system"] = ext_system
            return ok(data=platform.list_term_knowledges(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/term-knowledges", tags=["Term"])
    def create_term_knowledge(body: dict[str, Any]) -> Any:
        """Create a term knowledge entry."""
        try:
            return ok(
                data=platform.create_term_knowledge(_base(), knowledge=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/term-knowledges/{id}", tags=["Term"])
    def get_term_knowledge(id: str) -> Any:
        """Get a term knowledge entry by ID."""
        try:
            knowledge = platform.get_term_knowledge(_base(), knowledge_id=id)
            if knowledge is None:
                raise HTTPException(
                    status_code=404, detail=f"TermKnowledge '{id}' not found"
                )
            return ok(data=knowledge)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/term-knowledges/{id}", tags=["Term"])
    def update_term_knowledge(id: str, body: dict[str, Any]) -> Any:
        """Update a term knowledge entry."""
        try:
            platform.update_term_knowledge(_base(), knowledge_id=id, updates=body)
            return ok(data={"knowledgeId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/term-knowledges/{id}", tags=["Term"])
    def delete_term_knowledge(id: str) -> Any:
        """Delete a term knowledge entry."""
        try:
            platform.delete_term_knowledge(_base(), knowledge_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # ══════════════════════════════════════════════════
    # Domain CRUD (6 endpoints)
    # ══════════════════════════════════════════════════

    @router.get("/domains", tags=["Term"])
    def list_domains(
        parent_id: str | None = Query(default=None),
    ) -> Any:
        """List domains with optional parent filter."""
        try:
            kwargs: dict[str, Any] = {}
            if parent_id is not None:
                kwargs["parent_id"] = parent_id
            return ok(data=platform.list_domains(_base(), **kwargs))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/domains", tags=["Term"])
    def create_domain(body: dict[str, Any]) -> Any:
        """Create a domain."""
        try:
            return ok(
                data=platform.create_domain(_base(), domain=body),
                message="created",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/domains/{id}", tags=["Term"])
    def get_domain(id: str) -> Any:
        """Get a domain by ID."""
        try:
            domain = platform.get_domain(_base(), domain_id=id)
            if domain is None:
                raise HTTPException(status_code=404, detail=f"Domain '{id}' not found")
            return ok(data=domain)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/domains/{id}", tags=["Term"])
    def update_domain(id: str, body: dict[str, Any]) -> Any:
        """Update a domain."""
        try:
            platform.update_domain(_base(), domain_id=id, updates=body)
            return ok(data={"domainId": id})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.delete("/domains/{id}", tags=["Term"])
    def delete_domain(id: str) -> Any:
        """Delete a domain."""
        try:
            platform.delete_domain(_base(), domain_id=id)
            return ok(message="deleted")
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.get("/domains/{id}/term-types", tags=["Term"])
    def list_domain_term_types(id: str) -> Any:
        """List term types under a domain."""
        try:
            return ok(data=platform.list_domain_term_types(_base(), domain_id=id))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
