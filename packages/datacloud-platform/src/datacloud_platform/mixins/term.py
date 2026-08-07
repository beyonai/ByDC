"""TermMixin — 术语库原子操作编排（薄封装层）。

每个方法直接委托到 TermBackend，不做编排。
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.sync import TermSyncHandler

import logging

from datacloud_platform.backends._contracts import _HasTermBackend
from datacloud_platform.models.graph_query import GraphQueryOptions

logger = logging.getLogger(__name__)


class TermMixin(TermSyncHandler):
    """Mixin for term-level atomic operations.

    Thin wrapper over TermBackend — 每个方法 = 一次 backend 调用，不做编排。
    同时实现 TermSyncHandler 协议，可作为 term_sync_worker 的 handler。
    """

    # ── Term ───────────────────────────────────────────────────────

    def search_terms(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).search_terms(**kwargs)

    def search_terms_batch(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).search_terms_batch(**kwargs)

    def search_terms_by_labels(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """按 term_tags 纯标签过滤术语，不触发文本检索。"""
        return self._term_for(base_id).search_terms_by_labels(**kwargs)

    def get_term_detail(
        self: _HasTermBackend, base_id: str, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_detail(
            library_id=library_id, term_id=term_id
        )

    def list_terms(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_terms(**kwargs)

    def create_term(
        self: _HasTermBackend, base_id: str, *, term: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term(term=term)

    def import_terms(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        terms: list[dict[str, Any]],
        backfill: bool = False,
    ) -> dict[str, Any]:
        return self._term_for(base_id).import_terms(
            library_id=library_id, terms=terms, backfill=backfill
        )

    def update_term(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str = "",
        term_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term(
            library_id=library_id, term_id=term_id, updates=updates
        )

    def delete_term(self: _HasTermBackend, base_id: str, *, term_id: str) -> None:
        self._term_for(base_id).delete_term(term_id=term_id)

    def query_term_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).query_term_relations(**kwargs)

    def query_term_relations_tree(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).query_term_relations_tree(**kwargs)

    # ── TermRelation ───────────────────────────────────────────────

    def list_term_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_relations(**kwargs)

    def get_term_relation(
        self: _HasTermBackend,
        base_id: str,
        *,
        relation_id: str,
        strict: bool = False,
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_relation(
            relation_id=relation_id,
            strict=strict,
        )

    def create_term_relation(
        self: _HasTermBackend, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_relation(relation=relation)

    def update_term_relation(
        self: _HasTermBackend,
        base_id: str,
        *,
        relation_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_relation(
            relation_id=relation_id, updates=updates
        )

    def delete_term_relation(
        self: _HasTermBackend, base_id: str, *, relation_id: str
    ) -> None:
        self._term_for(base_id).delete_term_relation(relation_id=relation_id)

    # ── TermName ───────────────────────────────────────────────────

    def list_term_names(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_names(**kwargs)

    def get_term_name(
        self: _HasTermBackend, base_id: str, *, name_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_name(name_id=name_id)

    def create_term_name(
        self: _HasTermBackend, base_id: str, *, name: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_name(name=name)

    def update_term_name(
        self: _HasTermBackend, base_id: str, *, name_id: str, updates: dict[str, Any]
    ) -> None:
        self._term_for(base_id).update_term_name(name_id=name_id, updates=updates)

    def delete_term_name(self: _HasTermBackend, base_id: str, *, name_id: str) -> None:
        self._term_for(base_id).delete_term_name(name_id=name_id)

    # ── TermKnowledge ──────────────────────────────────────────────

    def list_term_knowledges(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_knowledges(**kwargs)

    def get_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_knowledge(knowledge_id=knowledge_id)

    def create_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_knowledge(knowledge=knowledge)

    def update_term_knowledge(
        self: _HasTermBackend,
        base_id: str,
        *,
        knowledge_id: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_knowledge(
            knowledge_id=knowledge_id, updates=updates
        )

    def delete_term_knowledge(
        self: _HasTermBackend, base_id: str, *, knowledge_id: str
    ) -> None:
        self._term_for(base_id).delete_term_knowledge(knowledge_id=knowledge_id)

    # ── TermLibrary ────────────────────────────────────────────────

    def list_term_libraries(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_term_libraries(**kwargs)

    def get_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_library(library_id=library_id)

    def create_term_library(
        self: _HasTermBackend, base_id: str, *, library: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_library(library=library)

    def update_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str, updates: dict[str, Any]
    ) -> None:
        self._term_for(base_id).update_term_library(
            library_id=library_id, updates=updates
        )

    def delete_term_library(
        self: _HasTermBackend, base_id: str, *, library_id: str
    ) -> None:
        self._term_for(base_id).delete_term_library(library_id=library_id)

    # ── TermType ───────────────────────────────────────────────────

    def list_term_types(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_types(**kwargs)

    def get_term_type(
        self: _HasTermBackend, base_id: str, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_term_type(
            library_id=library_id, type_code=type_code
        )

    def list_term_type_relations(
        self: _HasTermBackend, base_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        return self._term_for(base_id).list_term_type_relations(**kwargs)

    def create_term_type(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        term_type: dict[str, Any],
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_term_type(
            library_id=library_id, term_type=term_type
        )

    def update_term_type(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        type_code: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_term_type(
            library_id=library_id, type_code=type_code, updates=updates
        )

    def delete_term_type(
        self: _HasTermBackend, base_id: str, *, library_id: str, type_code: str
    ) -> None:
        self._term_for(base_id).delete_term_type(
            library_id=library_id, type_code=type_code
        )

    # ── Domain ─────────────────────────────────────────────────────

    def list_domains(
        self: _HasTermBackend, base_id: str, *, library_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self._term_for(base_id).list_domains(library_id=library_id, **kwargs)

    def get_domain(
        self: _HasTermBackend, base_id: str, *, library_id: str, domain_code: str
    ) -> dict[str, Any] | None:
        return self._term_for(base_id).get_domain(
            library_id=library_id, domain_code=domain_code
        )

    def create_domain(
        self: _HasTermBackend, base_id: str, *, domain: dict[str, Any]
    ) -> dict[str, Any]:
        return self._term_for(base_id).create_domain(domain=domain)

    def update_domain(
        self: _HasTermBackend,
        base_id: str,
        *,
        library_id: str,
        domain_code: str,
        updates: dict[str, Any],
    ) -> None:
        self._term_for(base_id).update_domain(
            library_id=library_id, domain_code=domain_code, updates=updates
        )

    def delete_domain(
        self: _HasTermBackend, base_id: str, *, library_id: str, domain_code: str
    ) -> None:
        self._term_for(base_id).delete_domain(
            library_id=library_id, domain_code=domain_code
        )

    # ── Vector ─────────────────────────────────────────────────────

    def embed(self: _HasTermBackend, base_id: str, text: str) -> list[float]:
        return self._term_for(base_id).embed(text)

    def embed_batch(
        self: _HasTermBackend, base_id: str, texts: list[str]
    ) -> list[list[float]]:
        return self._term_for(base_id).embed_batch(texts)

    # ── Sync ───────────────────────────────────────────────────────

    def sync_terms(
        self: _HasTermBackend,
        base_id: str,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        self._term_for(base_id).sync_terms(
            entity_code,
            entity_name,
            entity_source,
            fields,
            backfill_vectors=backfill_vectors,
        )

    def remove_terms(self: _HasTermBackend, base_id: str, entity_code: str) -> None:
        self._term_for(base_id).remove_terms(entity_code)

    # ── TermSyncHandler 实现 ────────────────────────────────────────

    def ensure_term_type(
        self: _HasTermBackend, *, base_id: str, type_code: str, type_name: str
    ) -> None:
        self._term_for(base_id).ensure_term_type(
            base_id=base_id, type_code=type_code, type_name=type_name
        )

    def upsert_terms(
        self: _HasTermBackend, *, base_id: str, terms: list[dict[str, Any]]
    ) -> list[str]:
        return self._term_for(base_id).upsert_terms(base_id=base_id, terms=terms)

    def delete_terms(
        self: _HasTermBackend,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        self._term_for(base_id).delete_terms(
            base_id=base_id, term_ids=term_ids, terms=terms
        )

    def query_knowledge_graph(
        self: _HasTermBackend,
        base_id: str,
        *,
        options: GraphQueryOptions,
        keywords: list[str] | None = None,
        term_ids: list[str] | None = None,
        kb_ids: set[str] | None = None,
        disambiguation_mode: str = "auto",
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Orchestrate a knowledge graph query: search roots → expand relations.

        Args:
            base_id: The base/project identifier.
            options: Resolved GraphQueryOptions from profile + overrides.
            keywords: Keywords to search for root terms.
            term_ids: Specific term IDs to use as roots.
            kb_ids: Knowledge base IDs for filtering (label_filters + child_attrs).
            disambiguation_mode: "auto" (pick top-1) or "return_all" (multiple).
            relation_category: Optional relation category filter (ONTOLOGY/BUSINESS).

        Returns:
            {"root_terms": [...], "total_terms": int}
        """
        logger.info(
            "query_knowledge_graph: base_id=%s, keywords=%s, term_ids=%s, "
            "profile=%s, max_level=%d",
            base_id,
            keywords,
            term_ids,
            options.query_profile,
            options.max_level,
        )

        # Build label_filters from kb_ids
        label_filters: list[dict[str, Any]] | None = None
        if kb_ids:
            label_filters = [
                {"field_code": "kb_id", "filter_value": str(kbid)} for kbid in kb_ids
            ]

        root_visited: set[str] = set()
        root_terms: list[dict[str, Any]] = []

        # ── 1. Search by keywords (batch) ────────────────────────────
        if keywords:
            batch_results = self._term_for(base_id).search_terms_batch(
                keywords=keywords,
                query_type="mixed",
                top_k=options.top_k,
                label_filters=label_filters,
                label_condition="or",
            )
            for keyword in keywords:
                search_result: Any = batch_results.get(keyword)
                if search_result is None:
                    continue

                # Handle both QueryResult dataclass and dict returns
                result_items: Any
                if hasattr(search_result, "items"):
                    result_items = search_result.items
                elif hasattr(search_result, "get"):
                    result_items = search_result.get("items", [])
                else:
                    result_items = []

                if not result_items:
                    continue

                # Post-filter by kb_ids (ext_attrs.kb_id check)
                if kb_ids:
                    filtered_items: list[Any] = []
                    for item in result_items:
                        item_ext_attrs: Any = (
                            item.ext_attrs
                            if hasattr(item, "ext_attrs")
                            else item.get("ext_attrs", {})
                            if hasattr(item, "get")
                            else {}
                        )
                        item_kb_id = ""
                        if isinstance(item_ext_attrs, dict):
                            item_kb_id = str(item_ext_attrs.get("kb_id", ""))
                        elif hasattr(item_ext_attrs, "kb_id"):
                            item_kb_id = str(item_ext_attrs.kb_id)
                        if item_kb_id in kb_ids:
                            filtered_items.append(item)
                    result_items = filtered_items

                if not result_items:
                    continue

                # Exact name/code matching for better disambiguation
                exact_matches: list[Any] = []
                for item in result_items:
                    term_name = (
                        item.term_name
                        if hasattr(item, "term_name")
                        else item.get("term_name", "")
                        if hasattr(item, "get")
                        else ""
                    )
                    term_code = (
                        item.term_code
                        if hasattr(item, "term_code")
                        else item.get("term_code", "")
                        if hasattr(item, "get")
                        else ""
                    )
                    if term_name and term_name.lower() == keyword.lower():
                        exact_matches.append(item)
                    elif term_code and term_code.lower() == keyword.lower():
                        exact_matches.append(item)

                # Apply disambiguation: "return_all" or top-1
                candidate_items: list[Any]
                if exact_matches:
                    if disambiguation_mode == "return_all":
                        candidate_items = exact_matches[: options.max_candidates]
                    else:
                        candidate_items = [exact_matches[0]]
                else:
                    if disambiguation_mode == "return_all":
                        candidate_items = result_items[: options.max_candidates]
                    else:
                        candidate_items = [result_items[0]]

                # Build root terms from candidates
                for term_item in candidate_items:
                    term_id: str = (
                        term_item.term_id
                        if hasattr(term_item, "term_id")
                        else term_item.get("term_id", "")
                        if hasattr(term_item, "get")
                        else ""
                    )
                    if not term_id or term_id in root_visited:
                        continue

                    # Get full term detail via backend
                    term_detail = self._term_for(base_id).get_term_detail(
                        library_id=base_id, term_id=term_id
                    )
                    attrs: dict[str, Any] = {}
                    if term_detail:
                        if hasattr(term_detail, "ext_attrs"):
                            attrs = term_detail.ext_attrs or {}
                        elif hasattr(term_detail, "get"):
                            attrs = term_detail.get("ext_attrs") or {}
                    if not isinstance(attrs, dict):
                        attrs = {}

                    term_name = (
                        term_item.term_name
                        if hasattr(term_item, "term_name")
                        else term_item.get("term_name", "")
                        if hasattr(term_item, "get")
                        else ""
                    )
                    root_term: dict[str, Any] = {
                        "term_id": term_id,
                        "term_name": term_name,
                        "term_code": (
                            term_item.term_code
                            if hasattr(term_item, "term_code")
                            else term_item.get("term_code", "")
                            if hasattr(term_item, "get")
                            else ""
                        ),
                        "term_type": (
                            term_item.term_type
                            if hasattr(term_item, "term_type")
                            else term_item.get("term_type", "")
                            if hasattr(term_item, "get")
                            else ""
                        ),
                        "attributes": attrs,
                        "path": term_name,
                        "depth": 0,
                        "seg": str(len(root_terms) + 1),
                    }
                    root_terms.append(root_term)
                    root_visited.add(term_id)

                logger.debug(
                    "Keyword '%s': %d root terms collected so far",
                    keyword,
                    len(root_terms),
                )

        # ── 2. Inject by term_ids ─────────────────────────────────────
        if term_ids:
            for tid in term_ids:
                if tid in root_visited:
                    continue
                term_detail = self._term_for(base_id).get_term_detail(
                    library_id=base_id, term_id=tid
                )
                if not term_detail:
                    continue

                tid_attrs: dict[str, Any] = {}
                if hasattr(term_detail, "ext_attrs"):
                    tid_attrs = term_detail.ext_attrs or {}
                elif hasattr(term_detail, "get"):
                    tid_attrs = term_detail.get("ext_attrs") or {}
                if not isinstance(tid_attrs, dict):
                    tid_attrs = {}

                # KB filtering for term_ids
                if kb_ids:
                    term_kb_id = str(tid_attrs.get("kb_id", ""))
                    if term_kb_id not in kb_ids:
                        continue

                term_name = (
                    term_detail.term_name
                    if hasattr(term_detail, "term_name")
                    else term_detail.get("term_name", "")
                    if hasattr(term_detail, "get")
                    else ""
                )
                root_term = {
                    "term_id": tid,
                    "term_name": term_name,
                    "term_code": (
                        term_detail.term_code
                        if hasattr(term_detail, "term_code")
                        else term_detail.get("term_code", "")
                        if hasattr(term_detail, "get")
                        else ""
                    ),
                    "term_type": (
                        term_detail.term_type
                        if hasattr(term_detail, "term_type")
                        else term_detail.get("term_type", "")
                        if hasattr(term_detail, "get")
                        else ""
                    ),
                    "attributes": tid_attrs,
                    "path": term_name,
                    "depth": 0,
                    "seg": str(len(root_terms) + 1),
                }
                root_terms.append(root_term)
                root_visited.add(tid)

        if not root_terms:
            logger.info("query_knowledge_graph: no root terms found")
            return {"root_terms": [], "total_terms": 0}

        # ── 3. Expand relations for each root ─────────────────────────
        for root_term in root_terms:
            relation_visited: set[str] = {root_term["term_id"]}
            relations = TermMixin._fetch_relations_recursive(
                platform=self,
                base_id=base_id,
                term_id=root_term["term_id"],
                term_name=root_term["term_name"],
                current_path=root_term["term_name"],
                current_level=1,
                max_level=options.max_level,
                parent_seg=root_term["seg"],
                relation_visited=relation_visited,
                kb_ids=kb_ids,
                max_edges=options.max_edges_per_root,
                direction=options.direction,
                relation_category=relation_category,
            )
            root_term["graph"] = relations
            root_term["max_depth"] = max((r["depth"] for r in relations), default=0)

        total_terms = sum(len(rt["graph"]) for rt in root_terms) + len(root_terms)
        logger.info(
            "query_knowledge_graph: %d root terms, %d total terms",
            len(root_terms),
            total_terms,
        )
        return {"root_terms": root_terms, "total_terms": total_terms}

    @staticmethod
    def _fetch_relations_recursive(
        platform: Any,
        base_id: str,
        term_id: str,
        term_name: str,
        current_path: str,
        current_level: int,
        max_level: int,
        parent_seg: str,
        relation_visited: set[str],
        kb_ids: set[str] | None = None,
        max_edges: int = 100,
        direction: str = "both",
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]:
        """BFS-based relation expansion using query_term_relations_tree (CTE).

        Each root term gets independent relation_visited set.
        kb_ids filtering is applied per child's ext_attrs.kb_id.
        max_edges truncates after that many edges are collected.
        """
        if current_level > max_level:
            return []

        tree_data = platform.query_term_relations_tree(
            base_id,
            term_id=term_id,
            max_depth=max_level - current_level + 1,
            relation_category=relation_category,
            direction=direction,
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
            if not next_id or next_id in relation_visited or next_id in node_info:
                continue

            source_id = edge.get("source_term_id", "")
            target_id = edge.get("target_term_id", "")
            relation_name = edge.get("relation_name", "")
            depth = edge.get("depth", 1)

            # Determine parent and child
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
                continue

            # kb_ids filtering: check child_attrs.kb_id BEFORE adding to visited
            if kb_ids:
                kb_id = (
                    child_attrs.get("kb_id", "")
                    if isinstance(child_attrs, dict)
                    else ""
                )
                if str(kb_id) not in kb_ids:
                    continue  # Do NOT add to visited

            if len(result) >= max_edges:
                break

            relation_visited.add(child_id)

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
