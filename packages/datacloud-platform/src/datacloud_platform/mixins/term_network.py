"""TermConnectionNetworkMixin — 术语连接网络图谱计算。

实现 source_terms → target_terms 的路径搜索和桥接词计算，
返回带评分的连接路径、桥接节点、知识引用和连接摘要。
"""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any

from datacloud_platform.backends._contracts import _HasTermBackend
from datacloud_platform.models.term_network import (
    GENERIC_NODE_PENALTY_PATTERNS,
    HUB_THRESHOLD,
    MAX_EDGES,
    RELATION_WEIGHTS,
    Edge,
    Gap,
    Path,
    PathEdge,
    PathNode,
    ResolvedTerm,
)

logger = logging.getLogger(__name__)

# UUID regex for detecting term IDs in seed lists.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Progressive depth for bridge-finding (1.4.3 第一层: 不限深).
# Start shallow, double each step until bridge nodes found or hard cap.
_BRIDGE_DEPTH_INITIAL: int = 3
_BRIDGE_DEPTH_HARD_CAP: int = 64

# Maximum raw paths to enumerate before early-exit in DFS.
# Prevent combinatorial explosion on dense subgraphs.
_MAX_RAW_PATHS: int = 5000


class TermConnectionNetworkMixin:
    """Mixin providing term connection network computation.

    Computes source-to-target paths with bridge nodes, path scoring,
    knowledge refs, and a connection summary for downstream Agent use.
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def get_term_connection_network(
        self: _HasTermBackend,
        base_id: str,
        *,
        source_terms: list[str],
        target_terms: list[str],
        kb_ids: list[str] | None = None,
        max_depth: int = 3,
        max_paths: int = 12,
        direction: str = "both",
        relation_names: list[str] | None = None,
        bridge_terms: list[str] | None = None,
        relation_category: str | None = None,
        include_knowledge_refs: bool = True,
        include_debug: bool = False,
    ) -> dict[str, Any]:
        """Compute the term connection network between source and target terms.

        Args:
            base_id: The base/project identifier.
            source_terms: Start-point term names or UUIDs (at least 1).
            target_terms: End-point term names or UUIDs (at least 1).
            kb_ids: Knowledge base ID filter list. Defaults to ["78"].
            max_depth: Maximum path hops (1-4, default 3).
            max_paths: Maximum number of paths returned (default 12).
            direction: Traversal direction ("out", "in", "both").
            relation_names: Path-level relation whitelist. None = no filter.
            bridge_terms: User-specified bridge terms for scoring weight only.
            relation_category: Relation category filter ("ONTOLOGY"/"BUSINESS").
                Maps from "metadata"/"instance" like getKnowledgeByTermWord.
                None = no filter.
            include_knowledge_refs: Return kb_id + kb_file_path per term.
            include_debug: Include resolution process in response.

        Returns:
            Success dict with source_nodes, target_nodes, bridge_nodes, paths,
            knowledge_refs, connection_summary, gaps.
            On error, returns ``{"success": False, "error": {...}}``.
        """
        kb_id_set: set[str] | None = set(kb_ids) if kb_ids else None

        # ── Step 1: Resolve source and target terms ──────────────────
        source_nodes, source_gaps = self._resolve_term_list(  # type: ignore[attr-defined]
            base_id=base_id, seeds=source_terms, kb_ids=kb_id_set
        )
        target_nodes, target_gaps = self._resolve_term_list(  # type: ignore[attr-defined]
            base_id=base_id, seeds=target_terms, kb_ids=kb_id_set
        )

        all_gaps = source_gaps + target_gaps

        if not source_nodes or not target_nodes:
            logger.warning(
                "Seed resolution failed: %d source, %d target resolved (base_id=%s)",
                len(source_nodes),
                len(target_nodes),
                base_id,
            )
            code = "NO_SOURCE_RESOLVED" if not source_nodes else "NO_TARGET_RESOLVED"
            return {
                "success": False,
                "error": {
                    "code": code,
                    "message": f"Resolved {len(source_nodes)} source(s) and "
                    f"{len(target_nodes)} target(s). Check term names.",
                    "detail": None,
                },
            }

        source_ids: set[str] = {rt.term_id for rt in source_nodes}
        target_ids: set[str] = {rt.term_id for rt in target_nodes}
        all_seed_ids = source_ids | target_ids

        logger.info(
            "Resolved %d source + %d target terms (%d gaps). Loading graph...",
            len(source_ids),
            len(target_ids),
            len(all_gaps),
        )

        # ── Step 2: Load graph edges (progressive depth) ────────────────
        # Try shallow depth first for bridge finding; deepen only if needed.
        adjacency: dict[str, list[Edge]] = {}
        all_edges: list[Edge] = []
        debug_info: dict[str, Any] = {}
        bridge_depth_used: int = _BRIDGE_DEPTH_INITIAL
        reachable_from_s: set[str] = set()
        reachable_from_t: set[str] = set()
        bridge_candidates: set[str] = set()
        prev_edge_count: int = -1

        depth_step = _BRIDGE_DEPTH_INITIAL
        while depth_step <= _BRIDGE_DEPTH_HARD_CAP:
            bridge_depth_used = depth_step
            effective_depth = max(depth_step, max_depth)

            adjacency, all_edges, _reached = self._load_connection_graph(  # type: ignore[attr-defined]
                base_id=base_id,
                seed_ids=all_seed_ids,
                max_depth=effective_depth,
                kb_ids=kb_id_set,
                direction=direction,
                relation_category=relation_category,
            )

            if not all_edges:
                depth_step *= 2
                continue

            # Quick check: any direct source↔target edge = sufficient.
            has_direct = any(
                (se.source in source_ids and se.target in target_ids)
                or (se.target in source_ids and se.source in target_ids)
                for edges in adjacency.values()
                for se in edges
            )

            # Compute bridge nodes with current depth.
            reachable_from_s = TermConnectionNetworkMixin._bfs_reachable(
                adjacency=adjacency, start_ids=source_ids, max_depth=None
            )
            reachable_from_t = TermConnectionNetworkMixin._bfs_reachable(
                adjacency=adjacency, start_ids=target_ids, max_depth=None
            )
            bridge_candidates = (
                (reachable_from_s & reachable_from_t) - source_ids - target_ids
            )

            if bridge_candidates or has_direct:
                break

            # Stop if no new edges were found (graph exhausted).
            cur_count = len(all_edges)
            if cur_count == prev_edge_count:
                logger.info("No new edges at depth=%d, stopping.", depth_step)
                break
            prev_edge_count = cur_count

            logger.info(
                "No bridge nodes at depth=%d, deepening... (S=%d, T=%d)",
                depth_step,
                len(reachable_from_s),
                len(reachable_from_t),
            )
            depth_step *= 2

        total_edges = len(all_edges)
        if total_edges == 0:
            logger.info("No edges found for base_id=%s", base_id)
            return {
                "success": False,
                "error": {
                    "code": "NO_EDGES_FOUND",
                    "message": "No edges found in the subgraph reachable from seeds.",
                    "detail": None,
                },
            }

        logger.info(
            "Loaded %d edges at bridge_depth=%d.", total_edges, bridge_depth_used
        )

        if include_debug:
            debug_info["total_edges_loaded"] = total_edges
            debug_info["bridge_depth_used"] = bridge_depth_used

        # ── Step 3: Compute bridge nodes ────────────────────────────────
        bridge_node_ids = bridge_candidates

        bridge_nodes = TermConnectionNetworkMixin._build_node_infos(
            adjacency=adjacency,
            node_ids=bridge_node_ids,
        )

        logger.info(
            "Bridge nodes: %d (S-reachable=%d, T-reachable=%d)",
            len(bridge_nodes),
            len(reachable_from_s),
            len(reachable_from_t),
        )

        if include_debug:
            debug_info["bridge_computation"] = {
                "s_reachable_count": len(reachable_from_s),
                "t_reachable_count": len(reachable_from_t),
                "bridge_candidate_count": len(bridge_node_ids),
                "bridge_nodes_count": len(bridge_nodes),
            }

        # ── Step 4: BFS path search (1.4.3 第二层: 限 max_depth) ─────
        subgraph_node_ids = source_ids | target_ids | bridge_node_ids

        all_paths = TermConnectionNetworkMixin._enumerate_paths(
            adjacency=adjacency,
            source_ids=source_ids,
            target_ids=target_ids,
            subgraph_node_ids=subgraph_node_ids,
            max_depth=max_depth,
            direction=direction,
        )

        logger.info("Found %d raw paths.", len(all_paths))

        # ── Step 5: Filter paths by relation_names (1.4.3 step 4) ──────
        if relation_names is not None:
            relation_set: set[str] = set(relation_names)
            all_paths = [
                p
                for p in all_paths
                if all(e.relation_name in relation_set for e in p.edges)
            ]
            logger.info(
                "After relation filter: %d paths (whitelist=%s)",
                len(all_paths),
                relation_names,
            )

        # ── Step 6: Score and sort paths ──────────────────────────────
        bridge_term_set: set[str] = set(bridge_terms) if bridge_terms else set()
        scored_paths = TermConnectionNetworkMixin._score_and_sort_paths(
            paths=all_paths,
            bridge_term_names=bridge_term_set,
            max_depth=max_depth,
            source_ids=source_ids,
            target_ids=target_ids,
        )
        top_paths = scored_paths[:max_paths]

        if include_debug:
            debug_info["path_computation"] = {
                "raw_paths_found": len(all_paths),
                "paths_returned": len(top_paths),
                "max_paths": max_paths,
            }

        # ── Step 7: Knowledge refs ────────────────────────────────────
        knowledge_refs: list[dict[str, Any]] = []
        if include_knowledge_refs:
            knowledge_refs = (
                TermConnectionNetworkMixin._build_knowledge_refs_from_paths(
                    paths=top_paths,
                )
            )

        # ── Step 8: Connection summary ────────────────────────────────
        connection_summary = TermConnectionNetworkMixin._build_connection_summary(
            source_nodes=source_nodes,
            target_nodes=target_nodes,
            top_paths=top_paths,
        )

        # ── Step 9: Build response ────────────────────────────────────
        response = TermConnectionNetworkMixin._build_connection_response(
            source_nodes=source_nodes,
            target_nodes=target_nodes,
            bridge_nodes=bridge_nodes,
            paths=top_paths,
            knowledge_refs=knowledge_refs,
            connection_summary=connection_summary,
            gaps=all_gaps,
            include_debug=include_debug,
            debug_info=debug_info if include_debug else None,
        )
        response["success"] = True
        return response

    # ── Seed resolution ─────────────────────────────────────────────────

    def _resolve_term_list(
        self: _HasTermBackend,
        base_id: str,
        seeds: list[str],
        kb_ids: set[str] | None,
    ) -> tuple[list[ResolvedTerm], list[Gap]]:
        """Resolve a list of term names/UUIDs to ResolvedTerm objects.

        UUID pattern → ``get_term_detail`` lookup.
        Otherwise → ``search_terms`` exact match, scored by kb_id
        priority (+100), file path (+1).

        Args:
            base_id: The base/project identifier.
            seeds: Mixed term names and UUIDs.
            kb_ids: Optional knowledge base ID filter set (used for scoring).

        Returns:
            Tuple of (resolved_terms, gaps) where resolved_terms is deduplicated
            by term_id and sorted by match score.
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
                    rt = self._resolved_term_from_detail(seed, detail)  # type: ignore[attr-defined]
                    resolved.append(rt)
                    seen_ids.add(seed)
                else:
                    gaps.append(
                        Gap(term=seed, reason="no_exact_match", resolution="unresolved")
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
                    Gap(term=seed, reason="no_exact_match", resolution="unresolved")
                )
                continue

            # Score candidates
            candidates: list[tuple[int, ResolvedTerm]] = []
            for item in items:
                data = TermConnectionNetworkMixin._extract_item_data(item)
                if data["term_id"] in seen_ids:
                    continue

                score = 0
                if kb_ids is not None and data["kb_id"] in kb_ids:
                    score += 100
                if data["kb_file_path"]:
                    score += 1

                rt = ResolvedTerm(
                    term_id=data["term_id"],
                    term_name=data["term_name"],
                    term_type=data["term_type"],
                    kb_id=data["kb_id"],
                    kb_file_path=data["kb_file_path"],
                    matched_by="exact",
                )
                candidates.append((score, rt))

            candidates.sort(key=lambda c: c[0], reverse=True)
            if not candidates:
                gaps.append(
                    Gap(term=seed, reason="no_exact_match", resolution="unresolved")
                )
                continue

            for _score, rt in candidates:
                resolved.append(rt)
                seen_ids.add(rt.term_id)

        return resolved, gaps

    # ── Graph loading ────────────────────────────────────────────────────

    def _load_connection_graph(
        self: _HasTermBackend,
        base_id: str,
        seed_ids: set[str],
        max_depth: int,
        kb_ids: set[str] | None,
        direction: str,
        relation_category: str | None = None,
    ) -> tuple[dict[str, list[Edge]], list[Edge], set[str]]:
        """Load the term relation graph from all seeds in one batch CTE call.

        Uses ``query_term_relations_tree_batch`` (multi-root, text[] visited_ids)
        to avoid the N+1 per-seed query problem.

        Returns:
            Tuple of (adjacency dict, flat edge list, reached term IDs).
        """
        adjacency: dict[str, list[Edge]] = {}
        all_edges: list[Edge] = []
        seen_edge_keys: set[tuple[str, str, str]] = set()
        reached_ids: set[str] = set()
        total_edges = 0

        # Single call: multi-root CTE loads the entire subgraph at once.
        tree_result: Any = self._term_for(base_id).query_term_relations_tree_batch(
            term_ids=list(seed_ids),
            max_depth=max_depth,
            relation_category=relation_category,
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

            source_id = TermConnectionNetworkMixin._extract_field(
                edge_raw, "source_term_id", ""
            )
            target_id = TermConnectionNetworkMixin._extract_field(
                edge_raw, "target_term_id", ""
            )

            # Dedup: skip edges already seen.
            edge_key = (
                min(source_id, target_id),
                max(source_id, target_id),
                relation_name,
            )
            if edge_key in seen_edge_keys:
                continue
            seen_edge_keys.add(edge_key)

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

            source_ext = TermConnectionNetworkMixin._extract_field(
                edge_raw, "source_ext_attrs", {}
            )
            target_ext = TermConnectionNetworkMixin._extract_field(
                edge_raw, "target_ext_attrs", {}
            )
            source_attrs: dict[str, Any] = (
                source_ext if isinstance(source_ext, dict) else {}
            )
            target_attrs: dict[str, Any] = (
                target_ext if isinstance(target_ext, dict) else {}
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

            all_edges.append(edge)
            reached_ids.add(source_id)
            reached_ids.add(target_id)

            if direction == "out":
                adjacency.setdefault(edge.source, []).append(edge)
            elif direction == "in":
                adjacency.setdefault(edge.target, []).append(edge.reversed())
            else:  # "both"
                adjacency.setdefault(edge.source, []).append(edge)
                adjacency.setdefault(edge.target, []).append(edge.reversed())

            total_edges += 1

        logger.info(
            "Loaded %d edges, %d unique nodes (batch CTE, depth=%d).",
            total_edges,
            len(reached_ids),
            max_depth,
        )
        return adjacency, all_edges, reached_ids

    # ── Bridge node computation (1.4.3 第一层) ────────────────────────────

    @staticmethod
    def _bfs_reachable(
        adjacency: dict[str, list[Edge]],
        start_ids: set[str],
        max_depth: int | None = None,
    ) -> set[str]:
        """Undirected BFS from start_ids, returning all reachable node IDs.

        Args:
            adjacency: Undirected adjacency dict (term_id → list[Edge]).
            start_ids: Starting node IDs.
            max_depth: Maximum depth; None means unlimited.

        Returns:
            Set of all reachable node IDs (including start_ids).
        """
        if not start_ids:
            return set()

        visited: set[str] = set()
        q: deque[tuple[str, int]] = deque()

        for sid in start_ids:
            if sid in adjacency or sid in visited:
                visited.add(sid)
                q.append((sid, 0))

        while q:
            node, depth = q.popleft()

            if max_depth is not None and depth >= max_depth:
                continue

            # Hub stop: don't expand from super-hub intermediate nodes
            degree = len(adjacency.get(node, []))
            if degree > HUB_THRESHOLD and node not in start_ids:
                continue

            for edge in adjacency.get(node, []):
                neighbor = edge.other_end(node)
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                q.append((neighbor, depth + 1))

        return visited

    @staticmethod
    def _build_node_infos(
        adjacency: dict[str, list[Edge]],
        node_ids: set[str],
    ) -> list[dict[str, str]]:
        """Build term info dicts for a set of node IDs from adjacency data.

        Extracts term_name, term_type, kb_id, kb_file_path from the first
        edge that references each node.
        """
        node_info: dict[str, dict[str, str]] = {}
        for edges in adjacency.values():
            for edge in edges:
                for nid, name, ntype, attrs in [
                    (
                        edge.source,
                        edge.source_name,
                        edge.source_type,
                        edge.source_attrs,
                    ),
                    (
                        edge.target,
                        edge.target_name,
                        edge.target_type,
                        edge.target_attrs,
                    ),
                ]:
                    if nid in node_ids and nid not in node_info:
                        node_info[nid] = {
                            "term_id": nid,
                            "term_name": name,
                            "term_type": ntype,
                            "kb_id": str(attrs.get("kb_id", "")),
                            "kb_file_path": str(attrs.get("kb_file_path", "")),
                        }
        return [node_info[nid] for nid in node_ids if nid in node_info]

    # ── DFS path enumeration (1.4.3 第二层) ─────────────────────────────────────

    @staticmethod
    def _enumerate_paths(
        adjacency: dict[str, list[Edge]],
        source_ids: set[str],
        target_ids: set[str],
        subgraph_node_ids: set[str],
        max_depth: int,
        direction: str,
    ) -> list[Path]:
        """Multi-phase DFS path enumeration covering all subgraph connections.

        Three phases (generic, no hard-coded assumptions):
        1. S → T ∪ bridge  (primary connection + source-side context)
        2. T → S ∪ bridge  (reverse direction + target-side context)
        3. bridge → bridge  (top-K by degree, depth ≤ 2)

        Uses depth-first search with per-path visited tracking. Paths are
        deduplicated by ordered node-id sequence.
        """
        all_paths: list[Path] = []
        path_counter = 0
        seen_sig: set[tuple[str, ...]] = set()  # dedup by node-id chain
        bridge_node_ids = subgraph_node_ids - source_ids - target_ids

        def _dfs_from(
            start_ids: set[str],
            endpoint_ids: set[str],
            min_depth: int,
            depth_limit: int,
            *,
            bridge_ids: set[str] | None = None,
            bridge_min_depth: int = 2,
        ) -> None:
            """DFS with separate depth thresholds for bridge vs non-bridge endpoints.

            bridge_ids / bridge_min_depth: if provided, bridge endpoints require
            at least bridge_min_depth hops (avoids flooding with direct neighbours).
            """
            nonlocal path_counter
            for start in start_ids:
                if start not in adjacency:
                    continue
                init_v = frozenset({start})
                stack: list[tuple[str, list[Edge], frozenset[str]]] = [
                    (start, [], init_v)
                ]
                while stack:
                    if path_counter >= _MAX_RAW_PATHS:
                        return
                    node, edges, visited = stack.pop()
                    d = len(edges)

                    if node in endpoint_ids:
                        effective_min = (
                            bridge_min_depth
                            if bridge_ids is not None and node in bridge_ids
                            else min_depth
                        )
                        if d >= effective_min:
                            sig = TermConnectionNetworkMixin._path_sig(start, edges)
                            if sig not in seen_sig:
                                seen_sig.add(sig)
                                path_counter += 1
                                p = TermConnectionNetworkMixin._reconstruct_path_from_edges(
                                    path_id=f"p{path_counter}",
                                    path_edges=list(edges),
                                    direction=direction,
                                )
                                if p is not None:
                                    all_paths.append(p)

                    if d >= depth_limit:
                        continue

                    degree = len(adjacency.get(node, []))
                    if degree > HUB_THRESHOLD and node not in source_ids | target_ids:
                        continue

                    for edge in adjacency.get(node, []):
                        nb = edge.other_end(node)
                        if nb in visited or nb not in subgraph_node_ids:
                            continue
                        stack.append((nb, edges + [edge], visited | {nb}))

        # ── Phase 1: S → T (depth ≥ 1) + S → bridge (depth ≥ 2) ──
        _dfs_from(
            start_ids=source_ids,
            endpoint_ids=target_ids | bridge_node_ids,
            min_depth=1,
            depth_limit=max_depth,
            bridge_ids=bridge_node_ids,
            bridge_min_depth=2,
        )

        # ── Phase 2: T → S (depth ≥ 1) + T → bridge (depth ≥ 2) ──
        _dfs_from(
            start_ids=target_ids,
            endpoint_ids=source_ids | bridge_node_ids,
            min_depth=1,
            depth_limit=max_depth,
            bridge_ids=bridge_node_ids,
            bridge_min_depth=2,
        )

        # ── Phase 3: top-K bridge → all (depth ≥ 2) ──────────────────
        bridge_degree: list[tuple[int, str]] = sorted(
            (
                (len(adjacency.get(bid, [])), bid)
                for bid in bridge_node_ids
                if bid in adjacency
            ),
            reverse=True,
        )
        top_k_bridges = {bid for _, bid in bridge_degree[:10]}

        _dfs_from(
            start_ids=top_k_bridges,
            endpoint_ids=source_ids | target_ids | bridge_node_ids,
            min_depth=2,
            depth_limit=2,
        )

        return all_paths

    @staticmethod
    def _path_sig(start: str, edges: list[Edge]) -> tuple[str, ...]:
        """Build a canonical node-id chain for path deduplication."""
        sig: list[str] = [start]
        current = start
        for edge in edges:
            nxt = edge.other_end(current)
            sig.append(nxt)
            current = nxt
        return tuple(sig)

    @staticmethod
    def _reconstruct_path_from_edges(
        path_id: str,
        path_edges: list[Edge],
        direction: str,
    ) -> Path | None:
        """Reconstruct a Path from an ordered list of traversed edges.

        The edge list comes from DFS stack, each edge was traversed in
        some direction (which may differ from its original direction).
        This method recovers the node chain, preserves original edge
        directions, and builds the readable_path string.

        Args:
            path_id: Path identifier (e.g. "p1").
            path_edges: Ordered edges as traversed during DFS.
            direction: Original traversal direction parameter (unused here).

        Returns:
            Path object or None if reconstruction fails.
        """
        if not path_edges:
            return None

        # Determine the start node: the first edge's endpoint NOT shared
        # with the second edge (or arbitrarily pick if only one edge).
        first_edge = path_edges[0]
        if len(path_edges) == 1:
            current = first_edge.source
        else:
            second_edge = path_edges[1]
            candidates = {first_edge.source, first_edge.target}
            second_set = {second_edge.source, second_edge.target}
            shared = candidates & second_set
            current = (
                (candidates - shared).pop()
                if shared and len(shared) == 1
                else first_edge.source
            )

        # Walk forward through edges, tracking traversal direction.
        path_nodes: list[PathNode] = []
        path_out_edges: list[PathEdge] = []

        # Get start node info from the first edge.
        if current == first_edge.source:
            start_info = (
                first_edge.source,
                first_edge.source_name,
                first_edge.source_type,
                first_edge.source_attrs,
            )
        else:
            start_info = (
                first_edge.target,
                first_edge.target_name,
                first_edge.target_type,
                first_edge.target_attrs,
            )
        path_nodes.append(
            PathNode(
                term_id=start_info[0],
                term_name=start_info[1],
                term_type=start_info[2],
                kb_id=str(start_info[3].get("kb_id", "")),
                kb_file_path=str(start_info[3].get("kb_file_path", "")),
            )
        )

        for edge in path_edges:
            # Determine traversal direction.
            if current == edge.source:
                # Forward: current → edge.target
                next_id = edge.target
                next_name = edge.target_name
                next_type = edge.target_type
                next_attrs = edge.target_attrs
            else:
                # Reverse: current ← edge.target (original: edge.source → edge.target)
                # We traversed from target back to source.
                next_id = edge.source
                next_name = edge.source_name
                next_type = edge.source_type
                next_attrs = edge.source_attrs

            path_nodes.append(
                PathNode(
                    term_id=next_id,
                    term_name=next_name,
                    term_type=next_type,
                    kb_id=str(next_attrs.get("kb_id", "")),
                    kb_file_path=str(next_attrs.get("kb_file_path", "")),
                )
            )

            # Store original edge direction.
            path_out_edges.append(
                PathEdge(
                    source_term_id=edge.source,
                    target_term_id=edge.target,
                    relation_name=edge.relation,
                )
            )

            current = next_id

        # Build readable_path with traversal direction markers.
        readable_parts: list[str] = []
        for i, pn in enumerate(path_nodes):
            readable_parts.append(pn.term_name)
            if i < len(path_out_edges):
                pe = path_out_edges[i]
                # Determine if edge was traversed forward or backward.
                if i + 1 < len(path_nodes):
                    traversed_fwd = pe.source_term_id == path_nodes[i].term_id
                else:
                    traversed_fwd = True
                if traversed_fwd:
                    readable_parts.append(f"--[{pe.relation_name}]-->")
                else:
                    readable_parts.append(f"<--[{pe.relation_name}]--")

        readable_path = " ".join(readable_parts)

        return Path(
            path_id=path_id,
            depth=len(path_out_edges),
            score=0.0,  # scored later
            readable_path=readable_path,
            nodes=path_nodes,
            edges=path_out_edges,
        )

    # ── Path scoring (1.4.4) ──────────────────────────────────────────────

    @staticmethod
    def _score_and_sort_paths(
        paths: list[Path],
        bridge_term_names: set[str],
        max_depth: int,
        source_ids: set[str],
        target_ids: set[str],
    ) -> list[Path]:
        """Score each path and sort descending by score.

        Scoring formula (1.4.4):
            score = 短路径分 + 关系权重 + 桥接词权重 + 证据完整度 - 泛节点惩罚
        Plus seed-bonus: +2.0 if path starts from S or ends at T
        (prioritises source/target-anchored paths over pure bridge paths).
        """
        for path in paths:
            path.score = TermConnectionNetworkMixin._score_single_path(
                path=path,
                bridge_term_names=bridge_term_names,
                max_depth=max_depth,
                source_ids=source_ids,
                target_ids=target_ids,
            )

        paths.sort(key=lambda p: p.score, reverse=True)
        return paths

    @staticmethod
    def _score_single_path(
        path: Path,
        bridge_term_names: set[str],
        max_depth: int,
        source_ids: set[str],
        target_ids: set[str],
    ) -> float:
        """Compute a relevance score for a single path.

        Factors:
        - 短路径分: (max_depth - depth + 1) × 3.0, shorter paths higher
        - 关系权重: sum of RELATION_WEIGHTS for each edge
        - 桥接词权重: +1.0 per node matching user-specified bridge_terms
        - 证据完整度: +0.5 if all nodes have kb_file_path
        - 泛节点惩罚: -2.0 per node matching GENERIC_NODE_PENALTY_PATTERNS
        - Seed bonus: +2.0 if path starts at S or ends at T (prioritises
          source/target-anchored paths over pure bridge paths)
        """
        score = 0.0

        # Short path bonus
        score += (max_depth - path.depth + 1) * 3.0

        # Relation weights
        for edge in path.edges:
            score += RELATION_WEIGHTS.get(edge.relation_name, 0.3)

        # Bridge term bonus (user-specified, for scoring only)
        for node in path.nodes:
            if node.term_name in bridge_term_names:
                score += 1.0

        # Evidence completeness
        if all(n.kb_file_path for n in path.nodes):
            score += 0.5

        # Generic node penalty
        for node in path.nodes:
            if any(
                pattern in node.term_name for pattern in GENERIC_NODE_PENALTY_PATTERNS
            ):
                score -= 2.0

        # Seed bonus: S→X or X→T paths get priority over pure bridge→bridge.
        if path.nodes and path.nodes[0].term_id in source_ids:
            score += 2.0
        if path.nodes and path.nodes[-1].term_id in target_ids:
            score += 2.0

        return score

    # ── Knowledge refs ────────────────────────────────────────────────────

    @staticmethod
    def _build_knowledge_refs_from_paths(
        paths: list[Path],
    ) -> list[dict[str, Any]]:
        """Build knowledge_refs list from term participation in returned paths.

        Each term gets a KnowledgeRef with the path_ids it appears in.
        """
        # Collect all terms from paths and their path_ids
        term_path_map: dict[str, tuple[str, str, str, str, set[str]]] = {}
        # term_id → (term_name, term_type, kb_id, kb_file_path, {path_ids})

        for path in paths:
            for node in path.nodes:
                key = node.term_id
                if key not in term_path_map:
                    term_path_map[key] = (
                        node.term_name,
                        node.term_type,
                        node.kb_id,
                        node.kb_file_path,
                        set(),
                    )
                term_path_map[key][4].add(path.path_id)

        refs: list[dict[str, Any]] = []
        seen: set[str] = set()

        for term_id, (name, ttype, kb_id, kb_path, path_ids) in term_path_map.items():
            if term_id in seen:
                continue
            seen.add(term_id)
            refs.append(
                {
                    "term_id": term_id,
                    "term_name": name,
                    "term_type": ttype,
                    "kb_id": kb_id,
                    "kb_file_path": kb_path,
                    "path_ids": sorted(path_ids),
                }
            )

        return refs

    # ── Connection summary ────────────────────────────────────────────────

    @staticmethod
    def _build_connection_summary(
        source_nodes: list[ResolvedTerm],
        target_nodes: list[ResolvedTerm],
        top_paths: list[Path],
    ) -> dict[str, str]:
        """Build connection_summary with one_sentence and writing_claim.

        one_sentence: Brief description of the overall connection.
        writing_claim: An inference claim for Agent writing use.
        """
        src_names = [rt.term_name for rt in source_nodes]
        tgt_names = [rt.term_name for rt in target_nodes]

        src_str = "、".join(src_names[:3])
        tgt_str = "、".join(tgt_names[:3])

        one_sentence = f"{src_str} 到 {tgt_str} 的连接网络"

        # Build writing_claim from top paths
        if top_paths:
            claims: list[str] = []
            for path in top_paths[:3]:
                claims.append(path.readable_path)
            writing_claim = "；".join(claims)
        else:
            writing_claim = ""

        return {"one_sentence": one_sentence, "writing_claim": writing_claim}

    # ── Response builder ──────────────────────────────────────────────────

    @staticmethod
    def _build_connection_response(
        source_nodes: list[ResolvedTerm],
        target_nodes: list[ResolvedTerm],
        bridge_nodes: list[dict[str, str]],
        paths: list[Path],
        knowledge_refs: list[dict[str, Any]],
        connection_summary: dict[str, str],
        gaps: list[Gap],
        include_debug: bool,
        debug_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the final API response dict."""
        # source_nodes
        source_out: list[dict[str, str]] = [
            {
                "term_id": rt.term_id,
                "term_name": rt.term_name,
                "term_type": rt.term_type,
                "kb_id": rt.kb_id,
                "kb_file_path": rt.kb_file_path,
                "matched_by": rt.matched_by,
            }
            for rt in source_nodes
        ]

        # target_nodes
        target_out: list[dict[str, str]] = [
            {
                "term_id": rt.term_id,
                "term_name": rt.term_name,
                "term_type": rt.term_type,
                "kb_id": rt.kb_id,
                "kb_file_path": rt.kb_file_path,
                "matched_by": rt.matched_by,
            }
            for rt in target_nodes
        ]

        # paths
        paths_out: list[dict[str, Any]] = []
        for path in paths:
            paths_out.append(
                {
                    "path_id": path.path_id,
                    "depth": path.depth,
                    "score": round(path.score, 2),
                    "readable_path": path.readable_path,
                    "nodes": [
                        {
                            "term_id": n.term_id,
                            "term_name": n.term_name,
                            "term_type": n.term_type,
                            "kb_id": n.kb_id,
                            "kb_file_path": n.kb_file_path,
                        }
                        for n in path.nodes
                    ],
                    "edges": [
                        {
                            "source_term_id": e.source_term_id,
                            "target_term_id": e.target_term_id,
                            "relation_name": e.relation_name,
                        }
                        for e in path.edges
                    ],
                }
            )

        # gaps
        gaps_out: list[dict[str, str]] = [
            {
                "term": g.term,
                "reason": g.reason,
                "resolution": g.resolution,
                "resolved_term_name": g.resolved_term_name,
            }
            for g in gaps
        ]

        response: dict[str, Any] = {
            "source_nodes": source_out,
            "target_nodes": target_out,
            "bridge_nodes": bridge_nodes,
            "paths": paths_out,
            "knowledge_refs": knowledge_refs,
            "connection_summary": connection_summary,
            "gaps": gaps_out,
        }

        if include_debug and debug_info:
            response["debug_info"] = debug_info

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

    @staticmethod
    def _extract_item_data(item: Any) -> dict[str, str]:
        """Extract term item fields from a search result item."""
        term_id = TermConnectionNetworkMixin._extract_field(item, "term_id", "")
        term_name = TermConnectionNetworkMixin._extract_field(item, "term_name", "")
        term_type = TermConnectionNetworkMixin._extract_field(item, "term_type", "")
        ext_attrs_raw = TermConnectionNetworkMixin._extract_field(item, "ext_attrs", {})
        ext_attrs: dict[str, Any] = (
            ext_attrs_raw if isinstance(ext_attrs_raw, dict) else {}
        )
        return {
            "term_id": str(term_id),
            "term_name": str(term_name),
            "term_type": str(term_type),
            "kb_id": str(ext_attrs.get("kb_id", "")),
            "kb_file_path": str(ext_attrs.get("kb_file_path", "")),
        }

    @staticmethod
    def _resolved_term_from_detail(term_id: str, detail: Any) -> ResolvedTerm:
        """Create a ResolvedTerm from a get_term_detail result."""
        term_name = TermConnectionNetworkMixin._extract_field(detail, "term_name", "")
        term_type = TermConnectionNetworkMixin._extract_field(detail, "term_type", "")
        ext_attrs_raw = TermConnectionNetworkMixin._extract_field(
            detail, "ext_attrs", {}
        )
        ext_attrs: dict[str, Any] = (
            ext_attrs_raw if isinstance(ext_attrs_raw, dict) else {}
        )
        return ResolvedTerm(
            term_id=term_id,
            term_name=str(term_name),
            term_type=str(term_type),
            kb_id=str(ext_attrs.get("kb_id", "")),
            kb_file_path=str(ext_attrs.get("kb_file_path", "")),
            matched_by="exact",
        )
