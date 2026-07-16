"""TermConnectionNetworkMixin — 术语连接网络查询编排。

提供 seeds-based subgraph scoring + best_edges 算法能力。
文本解释留给 Agent 层处理。
"""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any

from datacloud_platform.backends._contracts import _HasTermBackend
from datacloud_platform.models.term_network import (
    HUB_THRESHOLD,
    MAX_EDGES,
    PRIORITY_TERM_TYPES,
    CatalogEntry,
    Edge,
    Gap,
    ResolvedTerm,
    ScoredEdge,
    SuggestedSeed,
    SubgraphStats,
    _relation_quality,
)

logger = logging.getLogger(__name__)

# UUID regex for detecting term IDs in seeds list.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class TermConnectionNetworkMixin:
    """Mixin providing term connection network query.

    Computes top-N scored edges from a unified seeds list,
    plus an optional catalog of unshown connections.
    Only does algorithmic work (term resolution + subgraph scoring);
    text explanations are left to the Agent layer.
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def get_term_connection_network(
        self: _HasTermBackend,
        base_id: str,
        *,
        seeds: list[str],
        detail_level: str = "summary",
        max_depth: int = 3,
        max_best_edges: int = 20,
        direction: str = "both",
        relation_names: list[str] | None = None,
        kb_ids: set[str] | None = None,
        include_debug: bool = False,
        include_catalog: bool = False,
    ) -> dict[str, Any]:
        """Query the term connection subgraph from a unified seeds list.

        Args:
            base_id: The base/project identifier.
            seeds: Term names or UUIDs — resolved automatically.
            detail_level: Response detail ("summary" or "full").
            max_depth: Maximum BFS depth from each seed.
            max_best_edges: Maximum number of best edges to return.
            direction: Traversal direction ("out", "in", "both").
            relation_names: Optional relation name filter.
            kb_ids: Optional knowledge base ID filter set.
            include_debug: Include debug info in response.

        Returns:
            Success dict with seed_nodes, best_edges, catalog, meta, gaps.
            On error, returns ``{"success": False, "error": {...}}``.
        """
        # ── Step 1: Resolve seeds ────────────────────────────────────
        seed_nodes, gaps = self._resolve_seeds(  # type: ignore[attr-defined]
            base_id=base_id,
            seeds=seeds,
            kb_ids=kb_ids,
        )

        if not seed_nodes:
            logger.warning("No seeds resolved for base_id=%s", base_id)
            return {
                "success": False,
                "error": {
                    "code": "NO_SEEDS_RESOLVED",
                    "message": "No seeds could be resolved to known terms.",
                    "detail": None,
                },
            }

        seed_ids: set[str] = {rt.term_id for rt in seed_nodes}
        logger.info(
            "Resolved %d seeds (%d gaps). Loading graph...",
            len(seed_ids),
            len(gaps),
        )

        # ── Step 2: Load term graph ─────────────────────────────────
        adjacency = self._load_term_graph(  # type: ignore[attr-defined]
            base_id=base_id,
            source_ids=seed_ids,
            target_ids=seed_ids,
            max_depth=max_depth,
            kb_ids=kb_ids,
            relation_names=relation_names,
            direction=direction,
        )
        total_edges = sum(len(edges) for edges in adjacency.values())

        if total_edges == 0:
            logger.info("No edges found in subgraph for base_id=%s", base_id)
            return {
                "success": False,
                "error": {
                    "code": "NO_EDGES_FOUND",
                    "message": "No edges found in the subgraph reachable from seeds.",
                    "detail": None,
                },
            }

        logger.info("Loaded %d edges in subgraph.", total_edges)

        # ── Step 3: Collect subgraph stats ──────────────────────────
        stats = TermConnectionNetworkMixin._collect_stats(adjacency)

        # ── Step 4: Score edges ─────────────────────────────────────
        all_scored = TermConnectionNetworkMixin._score_edges(
            seeds=list(seed_ids),
            adjacency=adjacency,
            subgraph_stats=stats,
            max_depth=max_depth,
        )

        # ── Step 5: Truncate to best edges ──────────────────────────
        best_edges = all_scored[:max_best_edges]
        truncated = total_edges > max_best_edges

        # ── Step 6: Suggested seeds + optional catalog ───────────────
        best_edge_keys: set[tuple[str, str, str]] = {
            (
                min(se.edge.source, se.edge.target),
                max(se.edge.source, se.edge.target),
                se.edge.relation,
            )
            for se in best_edges
        }

        suggested_seeds = TermConnectionNetworkMixin._build_suggested_seeds(
            best_edges=best_edges,
            stats=stats,
            seed_ids=seed_ids,
            adjacency=adjacency,
        )

        pinned_catalog = TermConnectionNetworkMixin._build_pinned_catalog(
            adjacency=adjacency,
            best_edge_keys=best_edge_keys,
            best_edges=best_edges,
        )

        catalog_entries: list[CatalogEntry] = []
        if include_catalog and truncated:
            catalog_entries = TermConnectionNetworkMixin._build_catalog(
                adjacency=adjacency,
                best_edge_keys=best_edge_keys,
            )

        # ── Step 7: Build meta ──────────────────────────────────────
        meta: dict[str, Any] = {
            "total_edges_found": total_edges,
            "best_edges_returned": len(best_edges),
            "suggested_seeds_count": len(suggested_seeds),
            "detail_level": detail_level,
            "next_detail_level": "full" if detail_level == "summary" else None,
            "truncated": truncated,
            "max_depth": max_depth,
            "max_best_edges": max_best_edges,
        }

        # ── Step 8: Build response ──────────────────────────────────
        response = TermConnectionNetworkMixin._build_response(
            seed_nodes=seed_nodes,
            best_edges=best_edges,
            suggested_seeds=suggested_seeds,
            pinned_catalog=pinned_catalog,
            catalog_entries=catalog_entries,
            gaps=gaps,
            meta=meta,
            adjacency=adjacency,
            include_debug=include_debug,
        )
        response["success"] = True
        return response

    # ── Private helpers ──────────────────────────────────────────────────

    def _resolve_seeds(
        self: _HasTermBackend,
        base_id: str,
        seeds: list[str],
        kb_ids: set[str] | None,
    ) -> tuple[list[ResolvedTerm], list[Gap]]:
        """Resolve a unified seeds list to ResolvedTerm objects.

        Each seed is classified:
        - UUID pattern → ``get_term_detail`` lookup.
        - Otherwise → ``search_terms`` exact match, scored by kb_id
          priority (+100), term type (+10), file path (+1).

        Args:
            base_id: The base/project identifier.
            seeds: Mixed term names and UUIDs.
            kb_ids: Optional knowledge base ID filter set (used for scoring).

        Returns:
            Tuple of (resolved_terms, gaps).
        """
        resolved: list[ResolvedTerm] = []
        gaps: list[Gap] = []
        seen_ids: set[str] = set()

        for seed in seeds:
            # ── UUID → direct lookup ────────────────────────────────
            if _UUID_RE.match(seed):
                if seed in seen_ids:
                    continue
                detail = self._term_for(base_id).get_term_detail(
                    library_id=base_id, term_id=seed
                )
                if detail is not None:
                    term_name = TermConnectionNetworkMixin._extract_field(
                        detail, "term_name", ""
                    )
                    term_type = TermConnectionNetworkMixin._extract_field(
                        detail, "term_type", ""
                    )
                    ext_attrs_raw = TermConnectionNetworkMixin._extract_field(
                        detail, "ext_attrs", {}
                    )
                    ext_attrs: dict[str, Any] = (
                        ext_attrs_raw if isinstance(ext_attrs_raw, dict) else {}
                    )
                    kb_id = str(ext_attrs.get("kb_id", ""))
                    kb_file_path = str(ext_attrs.get("kb_file_path", ""))

                    rt = ResolvedTerm(
                        term_id=seed,
                        term_name=str(term_name),
                        term_type=str(term_type),
                        kb_id=kb_id,
                        kb_file_path=kb_file_path,
                        matched_by="exact",
                    )
                    resolved.append(rt)
                    seen_ids.add(seed)
                else:
                    gaps.append(
                        Gap(
                            term=seed,
                            reason="no_exact_match",
                            resolution="unresolved",
                        )
                    )
                continue

            # ── Name → search ───────────────────────────────────────
            search_result: Any = self._term_for(base_id).search_terms(
                keyword=seed, query_type="exact"
            )
            items: list[Any]
            if hasattr(search_result, "items"):
                items = list(search_result.items)
            elif isinstance(search_result, dict):
                items = list(search_result.get("items", []))
            else:
                items = []

            if not items:
                gaps.append(
                    Gap(
                        term=seed,
                        reason="no_exact_match",
                        resolution="unresolved",
                    )
                )
                continue

            # Score candidates
            candidates: list[tuple[int, dict[str, Any]]] = []
            for item in items:
                item_term_id = TermConnectionNetworkMixin._extract_field(
                    item, "term_id", ""
                )
                if item_term_id in seen_ids:
                    continue

                item_term_name = TermConnectionNetworkMixin._extract_field(
                    item, "term_name", ""
                )
                item_term_type = TermConnectionNetworkMixin._extract_field(
                    item, "term_type", ""
                )
                ext_attrs_raw = TermConnectionNetworkMixin._extract_field(
                    item, "ext_attrs", {}
                )
                item_ext_attrs: dict[str, Any] = (
                    ext_attrs_raw if isinstance(ext_attrs_raw, dict) else {}
                )
                item_kb_id = str(item_ext_attrs.get("kb_id", ""))
                item_kb_file_path = str(item_ext_attrs.get("kb_file_path", ""))

                score = 0
                if kb_ids is not None and item_kb_id in kb_ids:
                    score += 100
                if item_term_type in PRIORITY_TERM_TYPES:
                    score += 10
                if item_kb_file_path:
                    score += 1

                candidates.append(
                    (
                        score,
                        {
                            "term_id": str(item_term_id),
                            "term_name": str(item_term_name),
                            "term_type": str(item_term_type),
                            "kb_id": item_kb_id,
                            "kb_file_path": item_kb_file_path,
                        },
                    )
                )

            candidates.sort(key=lambda c: c[0], reverse=True)
            if not candidates:
                gaps.append(
                    Gap(
                        term=seed,
                        reason="no_exact_match",
                        resolution="unresolved",
                    )
                )
                continue

            for _score, data in candidates:
                rt = ResolvedTerm(
                    term_id=data["term_id"],
                    term_name=data["term_name"],
                    term_type=data["term_type"],
                    kb_id=data["kb_id"],
                    kb_file_path=data["kb_file_path"],
                    matched_by="exact",
                )
                resolved.append(rt)
                seen_ids.add(data["term_id"])

        return resolved, gaps

    def _load_term_graph(
        self: _HasTermBackend,
        base_id: str,
        source_ids: set[str],
        target_ids: set[str],
        max_depth: int,
        kb_ids: set[str] | None,
        relation_names: list[str] | None,
        direction: str,
    ) -> dict[str, list[Edge]]:
        """Load the term relation graph by expanding from seed term IDs.

        Uses query_term_relations_tree CTE for efficient graph loading.
        Applies relation_names, kb_ids, and max_edges filters.

        Returns:
            Adjacency dict mapping term_id → list of outgoing Edge objects.
        """
        adjacency: dict[str, list[Edge]] = {}
        total_edges = 0
        all_seed_ids = source_ids | target_ids

        for term_id in all_seed_ids:
            if total_edges >= MAX_EDGES:
                logger.warning("Reached MAX_EDGES=%d, stopping graph load.", MAX_EDGES)
                break

            tree_result: Any = self._term_for(base_id).query_term_relations_tree(
                term_id=term_id, max_depth=max_depth
            )
            edges_data: list[Any]
            if hasattr(tree_result, "data"):
                edges_data = list(tree_result.data)
            elif isinstance(tree_result, dict):
                edges_data = list(tree_result.get("data", []))
            else:
                edges_data = []

            for edge_raw in edges_data:
                if total_edges >= MAX_EDGES:
                    break

                relation_name = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "relation_name", ""
                )
                if relation_names is not None and relation_name not in relation_names:
                    continue

                source_id = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "source_term_id", ""
                )
                target_id = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "target_term_id", ""
                )
                source_name = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "source_term_name", ""
                )
                target_name = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "target_term_name", ""
                )
                source_type = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "source_term_type", ""
                )
                target_type = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "target_term_type", ""
                )

                source_ext_attrs_raw = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "source_ext_attrs", {}
                )
                target_ext_attrs_raw = TermConnectionNetworkMixin._extract_field(
                    edge_raw, "target_ext_attrs", {}
                )
                source_attrs: dict[str, Any] = (
                    source_ext_attrs_raw
                    if isinstance(source_ext_attrs_raw, dict)
                    else {}
                )
                target_attrs: dict[str, Any] = (
                    target_ext_attrs_raw
                    if isinstance(target_ext_attrs_raw, dict)
                    else {}
                )

                # kb_ids filter: at least one side must match
                if kb_ids is not None:
                    source_kb = str(source_attrs.get("kb_id", ""))
                    target_kb = str(target_attrs.get("kb_id", ""))
                    if source_kb not in kb_ids and target_kb not in kb_ids:
                        continue

                edge = Edge(
                    source=source_id,
                    target=target_id,
                    relation=relation_name,
                    source_name=source_name,
                    target_name=target_name,
                    source_type=source_type,
                    target_type=target_type,
                    source_attrs=source_attrs,
                    target_attrs=target_attrs,
                )

                if direction == "out":
                    adjacency.setdefault(edge.source, []).append(edge)
                elif direction == "in":
                    adjacency.setdefault(edge.target, []).append(edge.reversed())
                else:  # "both"
                    adjacency.setdefault(edge.source, []).append(edge)
                    adjacency.setdefault(edge.target, []).append(edge.reversed())

                total_edges += 1

        return adjacency

    @staticmethod
    def _collect_stats(adjacency: dict[str, list[Edge]]) -> SubgraphStats:
        """Collect relation frequency and node degree from adjacency.

        Args:
            adjacency: Term adjacency dict (term_id → list of Edge).

        Returns:
            SubgraphStats with relation_freq and node_degree.
        """
        relation_freq: dict[str, int] = {}
        node_degree: dict[str, int] = {}

        for edges in adjacency.values():
            for edge in edges:
                relation_freq[edge.relation] = relation_freq.get(edge.relation, 0) + 1
                node_degree[edge.source] = node_degree.get(edge.source, 0) + 1
                node_degree[edge.target] = node_degree.get(edge.target, 0) + 1

        return SubgraphStats(relation_freq=relation_freq, node_degree=node_degree)

    @staticmethod
    def _score_edges(
        seeds: list[str],
        adjacency: dict[str, list[Edge]],
        subgraph_stats: SubgraphStats,
        max_depth: int,
    ) -> list[ScoredEdge]:
        """Multi-source BFS scoring of edges reachable from seeds.

        Each canonical edge ``(min(src, tgt), max(src, tgt), relation)`` is
        scored by connectivity count, relation quality, and hub penalty.

        Args:
            seeds: Seed term IDs.
            adjacency: Term adjacency dict.
            subgraph_stats: Pre-computed subgraph statistics.
            max_depth: Maximum BFS depth from each seed.

        Returns:
            List of ScoredEdge sorted by score descending.
        """
        # Canonical key → connectivity count
        connectivity: dict[tuple[str, str, str], int] = {}
        # Canonical key → minimum hops from any seed
        min_hops: dict[tuple[str, str, str], int] = {}
        # Canonical key → representative Edge object
        edge_map: dict[tuple[str, str, str], Edge] = {}

        # Multi-source BFS: global visited per seed (each node visited at most
        # once per seed), with hub stop to prevent super-node explosion.
        for seed_id in seeds:
            q: deque[tuple[str, int]] = deque([(seed_id, 0)])  # (node, hops)
            seen: set[str] = {seed_id}

            while q:
                node, hops = q.popleft()

                if hops >= max_depth:
                    continue

                # Hub stop: don't expand from super-hub intermediate nodes
                if (
                    subgraph_stats.node_degree.get(node, 0) > HUB_THRESHOLD
                    and node not in seeds
                ):
                    continue

                for edge in adjacency.get(node, []):
                    neighbor = edge.other_end(node)
                    if neighbor in seen:
                        continue

                    key = (min(node, neighbor), max(node, neighbor), edge.relation)
                    connectivity[key] = connectivity.get(key, 0) + 1
                    nxt_hops = hops + 1
                    if key not in min_hops:
                        min_hops[key] = nxt_hops
                        edge_map[key] = edge

                    seen.add(neighbor)
                    q.append((neighbor, nxt_hops))

        # Build scored edges
        scored: list[ScoredEdge] = []
        for key, conn in connectivity.items():
            _, _, relation = key
            quality = _relation_quality(relation, subgraph_stats)
            edge = edge_map[key]
            src_deg = subgraph_stats.node_degree.get(edge.source, 0)
            tgt_deg = subgraph_stats.node_degree.get(edge.target, 0)
            hub = 2 if src_deg > HUB_THRESHOLD or tgt_deg > HUB_THRESHOLD else 0
            hops = min_hops[key]
            score = (conn / max(hops * hops, 1)) * 10.0 + quality - hub
            scored.append(
                ScoredEdge(edge=edge, score=score, hops_from_seed=min_hops[key])
            )

        scored.sort(key=lambda se: se.score, reverse=True)
        return scored

    @staticmethod
    def _build_catalog(
        adjacency: dict[str, list[Edge]],
        best_edge_keys: set[tuple[str, str, str]],
    ) -> list[CatalogEntry]:
        """Build catalog entries for edges not present in best_edges.

        Groups remaining edges by node and computes unshown_edge_count,
        deduplicated relations, and deduplicated neighbor names (max 10).

        Args:
            adjacency: Full adjacency dict.
            best_edge_keys: Canonical keys of edges already in best_edges.

        Returns:
            List of CatalogEntry objects.
        """
        # Group unshown edges by node
        node_edges: dict[str, list[Edge]] = {}
        for edges in adjacency.values():
            for edge in edges:
                key = (
                    min(edge.source, edge.target),
                    max(edge.source, edge.target),
                    edge.relation,
                )
                if key in best_edge_keys:
                    continue
                node_edges.setdefault(edge.source, []).append(edge)
                node_edges.setdefault(edge.target, []).append(edge)

        entries: list[CatalogEntry] = []
        for node_id, unshown_edges in node_edges.items():
            relations: list[str] = []
            neighbors: list[str] = []
            seen_rels: set[str] = set()
            seen_neighbors: set[str] = set()

            # Gather representative info from the first edge
            term_name = ""
            term_type = ""
            kb_file_path = ""

            for ue in unshown_edges:
                if ue.relation not in seen_rels:
                    seen_rels.add(ue.relation)
                    relations.append(ue.relation)

                neighbor_name = (
                    ue.target_name if ue.source == node_id else ue.source_name
                )
                if neighbor_name and neighbor_name not in seen_neighbors:
                    seen_neighbors.add(neighbor_name)
                    neighbors.append(neighbor_name)

                if not term_name:
                    term_name = (
                        ue.source_name if ue.source == node_id else ue.target_name
                    )
                if not term_type:
                    term_type = (
                        ue.source_type if ue.source == node_id else ue.target_type
                    )
                if not kb_file_path:
                    ext_attrs = (
                        ue.source_attrs if ue.source == node_id else ue.target_attrs
                    )
                    kb_file_path = str(ext_attrs.get("kb_file_path", ""))

            entries.append(
                CatalogEntry(
                    term_id=node_id,
                    term_name=term_name,
                    term_type=term_type,
                    kb_file_path=kb_file_path,
                    unshown_edge_count=len(unshown_edges),
                    unshown_relations=relations,
                    unshown_neighbors=neighbors[:10],
                )
            )

        return entries

    @staticmethod
    def _build_pinned_catalog(
        adjacency: dict[str, list[Edge]],
        best_edge_keys: set[tuple[str, str, str]],
        best_edges: list[ScoredEdge],
    ) -> list[CatalogEntry]:
        """Build catalog limited to nodes that appear in best_edges.

        Only collects unshown edges for nodes that are present in best_edges
        (as source or target). This gives the Agent visibility into what else
        these "familiar" nodes connect to, without flooding with 100+ entries.
        """
        # Collect node IDs from best_edges
        be_node_ids: set[str] = set()
        for se in best_edges:
            be_node_ids.add(se.edge.source)
            be_node_ids.add(se.edge.target)

        # Group unshown edges by node (only be_node_ids)
        node_edges: dict[str, list[Edge]] = {}
        for edges in adjacency.values():
            for edge in edges:
                key = (
                    min(edge.source, edge.target),
                    max(edge.source, edge.target),
                    edge.relation,
                )
                if key in best_edge_keys:
                    continue
                if edge.source in be_node_ids:
                    node_edges.setdefault(edge.source, []).append(edge)
                if edge.target in be_node_ids:
                    node_edges.setdefault(edge.target, []).append(edge)

        entries: list[CatalogEntry] = []
        for node_id, unshown_edges in node_edges.items():
            relations: list[str] = []
            neighbors: list[str] = []
            seen_rels: set[str] = set()
            seen_neighbors: set[str] = set()
            term_name = ""
            term_type = ""
            kb_file_path = ""

            for ue in unshown_edges:
                if ue.relation not in seen_rels:
                    seen_rels.add(ue.relation)
                    relations.append(ue.relation)
                neighbor_name = (
                    ue.target_name if ue.source == node_id else ue.source_name
                )
                if neighbor_name and neighbor_name not in seen_neighbors:
                    seen_neighbors.add(neighbor_name)
                    neighbors.append(neighbor_name)
                if not term_name:
                    term_name = (
                        ue.source_name if ue.source == node_id else ue.target_name
                    )
                if not term_type:
                    term_type = (
                        ue.source_type if ue.source == node_id else ue.target_type
                    )
                if not kb_file_path:
                    ext_attrs = (
                        ue.source_attrs if ue.source == node_id else ue.target_attrs
                    )
                    kb_file_path = str(ext_attrs.get("kb_file_path", ""))

            entries.append(
                CatalogEntry(
                    term_id=node_id,
                    term_name=term_name,
                    term_type=term_type,
                    kb_file_path=kb_file_path,
                    unshown_edge_count=len(unshown_edges),
                    unshown_relations=relations,
                    unshown_neighbors=neighbors[:10],
                )
            )

        return entries

    @staticmethod
    def _build_suggested_seeds(
        best_edges: list[ScoredEdge],
        stats: SubgraphStats,
        seed_ids: set[str],
        adjacency: dict[str, list[Edge]],
    ) -> list[SuggestedSeed]:
        """Generate routing suggestions from best_edges non-seed nodes.

        Picks non-seed nodes with degree > 10 from the best_edges, sorted by
        degree descending, returning the top 5 as SuggestedSeed objects.
        """
        candidates: list[tuple[int, str, str, int, str]] = []
        seen: set[str] = set()

        for se in best_edges:
            e = se.edge
            for node_id, node_name in [
                (e.source, e.source_name),
                (e.target, e.target_name),
            ]:
                if node_id in seed_ids or node_id in seen:
                    continue
                degree = stats.node_degree.get(node_id, 0)
                if degree <= 10:
                    continue
                seen.add(node_id)
                candidates.append(
                    (
                        degree,
                        node_id,
                        node_name,
                        se.hops_from_seed,
                        f"{degree} unshown edges — intermediate bridge",
                    )
                )

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [
            SuggestedSeed(
                term_id=tid,
                term_name=tname,
                reason=reason,
                hops_from_seed=hops,
            )
            for _, tid, tname, hops, reason in candidates[:5]
        ]

    @staticmethod
    def _build_response(
        seed_nodes: list[ResolvedTerm],
        best_edges: list[ScoredEdge],
        suggested_seeds: list[SuggestedSeed],
        pinned_catalog: list[CatalogEntry],
        catalog_entries: list[CatalogEntry],
        gaps: list[Gap],
        meta: dict[str, Any],
        adjacency: dict[str, list[Edge]],  # noqa: ARG004
        *,
        include_debug: bool,
    ) -> dict[str, Any]:
        """Build the final API response dict from resolved data.

        Args:
            seed_nodes: Resolved seed terms.
            best_edges: Top scored edges.
            catalog_entries: Catalog entries for unshown edges.
            gaps: Unresolved term gaps.
            meta: Pre-computed metadata dict (includes detail_level).
            adjacency: Full adjacency dict (for node info populating).
            include_debug: Whether to include debug info.

        Returns:
            Complete response dict.
        """
        detail_level: str = str(meta.get("detail_level", "summary"))

        # ── Build seed_nodes ──────────────────────────────────────
        seed_nodes_out: list[dict[str, str]] = [
            {
                "term_id": rt.term_id,
                "term_name": rt.term_name,
                "term_type": rt.term_type,
                "matched_by": rt.matched_by,
                "kb_id": rt.kb_id,
                "kb_file_path": rt.kb_file_path,
            }
            for rt in seed_nodes
        ]

        # ── Build best_edges ──────────────────────────────────────
        # Build source/target info lookup from edges
        node_type_lookup: dict[str, str] = {}
        for se in best_edges:
            e = se.edge
            node_type_lookup[e.source] = e.source_type
            node_type_lookup[e.target] = e.target_type

        best_edges_out: list[dict[str, Any]] = []
        for i, se in enumerate(best_edges):
            e = se.edge
            edge_dict: dict[str, Any] = {
                "edge_id": f"e{i + 1}",
                "source_term_id": e.source,
                "source_term_name": e.source_name,
                "target_term_id": e.target,
                "target_term_name": e.target_name,
                "relation_name": e.relation,
                "score": se.score,
                "hops_from_seed": se.hops_from_seed,
                "source_term_type": e.source_type,
                "target_term_type": e.target_type,
            }
            if detail_level == "full":
                edge_dict["source_attrs"] = e.source_attrs
                edge_dict["target_attrs"] = e.target_attrs
            best_edges_out.append(edge_dict)

        # ── Build catalog ─────────────────────────────────────────
        catalog_nodes: list[dict[str, Any]] = []
        for ce in catalog_entries:
            cn: dict[str, Any] = {
                "term_id": ce.term_id,
                "term_name": ce.term_name,
                "unshown_edge_count": ce.unshown_edge_count,
                "unshown_relations": ce.unshown_relations,
                "unshown_neighbors": ce.unshown_neighbors,
            }
            if detail_level == "full":
                cn["term_type"] = ce.term_type
                cn["kb_file_path"] = ce.kb_file_path
            catalog_nodes.append(cn)

        # ── Build gaps ────────────────────────────────────────────
        gaps_out: list[dict[str, str]] = [
            {
                "term": g.term,
                "reason": g.reason,
                "resolution": g.resolution,
                "resolved_term_name": g.resolved_term_name,
            }
            for g in gaps
        ]

        # ── Build suggested_seeds ────────────────────────────────
        ss_out: list[dict[str, Any]] = [
            {
                "term_id": ss.term_id,
                "term_name": ss.term_name,
                "reason": ss.reason,
                "hops_from_seed": ss.hops_from_seed,
            }
            for ss in suggested_seeds
        ]

        # ── Build pinned_catalog ─────────────────────────────────
        pinned_nodes: list[dict[str, Any]] = []
        for ce in pinned_catalog:
            pcn: dict[str, Any] = {
                "term_id": ce.term_id,
                "term_name": ce.term_name,
                "unshown_edge_count": ce.unshown_edge_count,
                "unshown_relations": ce.unshown_relations,
                "unshown_neighbors": ce.unshown_neighbors,
            }
            if detail_level == "full":
                pcn["term_type"] = ce.term_type
                pcn["kb_file_path"] = ce.kb_file_path
            pinned_nodes.append(pcn)

        # ── Assemble response ─────────────────────────────────────
        response: dict[str, Any] = {
            "seed_nodes": seed_nodes_out,
            "best_edges": best_edges_out,
            "suggested_seeds": ss_out,
            "pinned_catalog": {"nodes": pinned_nodes},
            "meta": meta,
            "gaps": gaps_out,
        }
        if catalog_entries:
            response["catalog"] = {"nodes": catalog_nodes}

        response["hints"] = _build_hints(
            meta,
            gaps_out,
            best_edges=best_edges_out,
            catalog_entries=catalog_entries,
            seed_node_names=[rt.term_name for rt in seed_nodes],
        )

        # ── Debug info ────────────────────────────────────────────
        if include_debug:
            response["debug_info"] = {
                "seeds_resolved": len(seed_nodes),
                "seeds_unresolved": len(gaps),
                "total_scored_edges": len(best_edges) + len(catalog_entries),
                "max_depth": meta.get("max_depth"),
                "max_best_edges": meta.get("max_best_edges"),
            }

        return response

    # ── Utility helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_field(obj: Any, field: str, default: Any = "") -> Any:
        """Safely extract a field from a dict or object, returning default on miss."""
        if hasattr(obj, field):
            return getattr(obj, field, default)
        if isinstance(obj, dict):
            return obj.get(field, default)
        return default


# ── Module-level helpers ───────────────────────────────────────────────


def _build_hints(
    meta: dict[str, Any],
    gaps: list[dict[str, str]],
    *,
    best_edges: list[dict[str, Any]],
    catalog_entries: list[CatalogEntry],
    seed_node_names: list[str],
) -> dict[str, Any]:
    """Generate data-driven usage hints based on actual query results.

    Analyses the returned edges and catalog to produce specific,
    actionable recommendations rather than generic field descriptions.
    """
    truncated = bool(meta.get("truncated", False))
    total = int(meta.get("total_edges_found", 0))
    returned = int(meta.get("best_edges_returned", 0))
    detail_level = str(meta.get("detail_level", "summary"))
    next_level = meta.get("next_detail_level")
    seed_set = set(seed_node_names)

    observations: list[str] = []
    suggestions: list[str] = []

    # ── 1. Direct connection check ─────────────────────────────
    direct_edges = [
        e
        for e in best_edges
        if e["source_term_name"] in seed_set and e["target_term_name"] in seed_set
    ]
    if direct_edges:
        edge_desc = ", ".join(
            f"{e['source_term_name']}↔{e['target_term_name']}({e['relation_name']})"
            for e in direct_edges[:5]
        )
        observations.append(f"✅ Direct connection found between seeds: {edge_desc}")
    else:
        observations.append(
            "⚠️ No direct edge connects any pair of seeds. "
            "The best_edges show intermediate paths — look for bridging terms."
        )

    # ── 2. Hub domination ──────────────────────────────────────
    node_best_count: dict[str, int] = {}
    for e in best_edges:
        node_best_count[e["source_term_name"]] = (
            node_best_count.get(e["source_term_name"], 0) + 1
        )
        node_best_count[e["target_term_name"]] = (
            node_best_count.get(e["target_term_name"], 0) + 1
        )
    dominant = [
        (n, c)
        for n, c in node_best_count.items()
        if c >= len(best_edges) * 0.3 and n not in seed_set
    ]
    if dominant:
        names = ", ".join(f"{n}(×{c})" for n, c in dominant[:3])
        observations.append(
            f"⚠️ Super-hub(s) dominate best_edges: {names}. "
            f"Their connections may be noise. Consider filtering with relation_names "
            f"to exclude low-signal relations or adding the hub as a seed for focused expansion."
        )

    # ── 3. Hops distribution ───────────────────────────────────
    hop1 = sum(1 for e in best_edges if e.get("hops_from_seed", 99) == 1)
    if hop1 == 0:
        observations.append(
            "No 1-hop edges found — seeds have no direct neighbours in this subgraph. "
            "Try increasing max_depth or adding related terms to seeds."
        )
    elif hop1 == len(best_edges):
        observations.append(
            f"All {returned} best_edges are 1-hop from seeds. "
            "This is the immediate neighbourhood. Increase max_depth to see multi-hop paths."
        )

    # ── 4. Catalog highlights ───────────────────────────────────
    big_catalog = [c for c in catalog_entries if c.unshown_edge_count >= 20]
    if big_catalog:
        item = max(big_catalog, key=lambda c: c.unshown_edge_count)
        observations.append(
            f"📊 '{item.term_name}' has {item.unshown_edge_count} unseen edges "
            f"(types: {', '.join(item.unshown_relations[:5])}). "
            f"It may be a knowledge hub — add it to seeds to explore its connections."
        )

    # ── Suggestions ─────────────────────────────────────────────
    if truncated:
        suggestion = (
            f"Showing {returned}/{total} edges. "
            f"To see more: (a) increase max_best_edges up to 200, "
            f"(b) narrow seeds to fewer terms, (c) reduce max_depth."
        )
        if total > 500:
            suggestion += (
                " The subgraph is large — reduce max_depth to 2 for a tighter view."
            )
        suggestions.append(suggestion)
    else:
        suggestions.append(
            "All found edges are shown. Try adding more seeds to broaden exploration."
        )

    if next_level == "full":
        suggestions.append(
            "Re-query with detail_level='full' to get kb_file_path for downloading cards."
        )
    elif next_level is None and detail_level == "full":
        suggestions.append(
            "You are at maximum detail. Use kb_file_path from edge attrs to download cards."
        )

    if gaps:
        unresolved = [g["term"] for g in gaps if g.get("resolution") == "unresolved"]
        if unresolved:
            suggestions.append(
                f"Unresolved seeds: {', '.join(unresolved)}. "
                f"Try search_terms(query_type='mixed') to find fuzzy matches, "
                f"then re-query with the resolved term_ids."
            )

    hints: dict[str, Any] = {
        "summary": "\n".join(observations) if observations else None,
        "suggestions": suggestions,
    }

    return hints
