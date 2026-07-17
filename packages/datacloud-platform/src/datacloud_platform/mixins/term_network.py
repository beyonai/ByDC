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

# Safety cap for path enumeration — prevents combinatorial explosion
# on hub nodes with many connections.
_MAX_PATHS_TOTAL: int = 500


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

        logger.info(
            "Resolved %d source + %d target terms (%d gaps). Loading graph...",
            len(source_ids),
            len(target_ids),
            len(all_gaps),
        )

        # ── Step 2: Load ALL edges in the product KB (flat query, no CTE) ──
        debug_info: dict[str, Any] = {}
        adjacency, all_edges, _reached = self._load_connection_graph(  # type: ignore[attr-defined]
            base_id=base_id,
            kb_ids=kb_id_set,
            direction=direction,
            relation_category=relation_category,
        )

        total_edges = len(all_edges)
        if total_edges == 0:
            logger.info("No edges found for base_id=%s", base_id)
            return {
                "success": False,
                "error": {
                    "code": "NO_EDGES_FOUND",
                    "message": "No edges found in the product KB.",
                    "detail": None,
                },
            }

        # ── Step 3: Compute bridge nodes (BFS intersection, unlimited depth) ──
        reachable_from_s = TermConnectionNetworkMixin._bfs_reachable(
            adjacency=adjacency, start_ids=source_ids, max_depth=None
        )
        reachable_from_t = TermConnectionNetworkMixin._bfs_reachable(
            adjacency=adjacency, start_ids=target_ids, max_depth=None
        )

        bridge_node_ids = (
            (reachable_from_s & reachable_from_t) - source_ids - target_ids
        )

        logger.info(
            "Loaded %d edges. Bridge nodes: %d (S-reachable=%d, T-reachable=%d).",
            total_edges,
            len(bridge_node_ids),
            len(reachable_from_s),
            len(reachable_from_t),
        )

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
        kb_ids: set[str] | None,
        direction: str,
        relation_category: str | None = None,
    ) -> tuple[dict[str, list[Edge]], list[Edge], set[str]]:
        """Load ALL edges in the product KB via a single flat query (no CTE).

        Uses ``query_edges_by_kb_id`` to fetch every edge where either endpoint
        belongs to one of the given kb_ids.  No recursion, no depth limits.

        Returns:
            Tuple of (adjacency dict, flat edge list, reached term IDs).
        """
        adjacency: dict[str, list[Edge]] = {}
        all_edges: list[Edge] = []
        seen_edge_keys: set[tuple[str, str, str]] = set()
        reached_ids: set[str] = set()
        total_edges = 0

        kb_id_list: list[str] = list(kb_ids) if kb_ids else []
        if not kb_id_list:
            logger.warning("No kb_ids provided, returning empty graph.")
            return adjacency, all_edges, reached_ids

        result: Any = self._term_for(base_id).query_edges_by_kb_id(
            kb_ids=kb_id_list,
            relation_category=relation_category,
        )
        edges_data: list[Any]
        if hasattr(result, "data"):
            edges_data = list(result.data)
        elif isinstance(result, dict):
            edges_data = list(result.get("data", []))
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
            "Loaded %d edges, %d unique nodes (flat query, kb_ids=%s).",
            total_edges,
            len(reached_ids),
            kb_id_list,
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

    # ── Path enumeration (1.4.3 第二层) ─────────────────────────────────────

    @staticmethod
    def _enumerate_paths(
        adjacency: dict[str, list[Edge]],
        source_ids: set[str],
        target_ids: set[str],
        subgraph_node_ids: set[str],
        max_depth: int,
        direction: str,
    ) -> list[Path]:
        """BFS from each source, recording all S→T and S→bridge paths.

        Two-pass BFS:
        - Pass 1: S → (T ∪ bridge)  — source-anchored paths
        - Pass 2: T → (S ∪ bridge)  — target-anchored paths (reverse perspective)
        """
        all_paths: list[Path] = []
        path_counter = 0
        seen_sig: set[tuple[str, ...]] = set()
        bridge_node_ids = subgraph_node_ids - source_ids - target_ids

        def _record(path_edges: list[Edge], start: str) -> None:
            nonlocal path_counter
            sig = TermConnectionNetworkMixin._path_sig(start, path_edges)
            if sig in seen_sig:
                return
            seen_sig.add(sig)
            path_counter += 1
            p = TermConnectionNetworkMixin._reconstruct_path_from_edges(
                path_id=f"p{path_counter}",
                path_edges=list(path_edges),
                direction=direction,
            )
            if p is not None:
                all_paths.append(p)

        def _bfs_pass(
            start_ids: set[str],
            endpoint_ids: set[str],
            *,
            bridge_ids: set[str] | None = None,
        ) -> None:
            """BFS from each start — single parent per node, one path per endpoint."""
            for start in start_ids:
                if start not in adjacency or path_counter >= _MAX_PATHS_TOTAL:
                    return
                parent: dict[str, tuple[str, Edge | None]] = {start: (start, None)}
                visited: set[str] = {start}
                q: deque[tuple[str, int]] = deque([(start, 0)])
                while q and path_counter < _MAX_PATHS_TOTAL:
                    node, d = q.popleft()
                    if d >= max_depth:
                        continue
                    # Hub stop for path search only — not in bridge computation
                    degree = len(adjacency.get(node, []))
                    if (
                        degree > HUB_THRESHOLD
                        and node not in source_ids | target_ids
                        and d > 0
                    ):
                        continue
                    for e in adjacency.get(node, []):
                        nb = e.other_end(node)
                        if nb in visited or nb not in subgraph_node_ids:
                            continue
                        visited.add(nb)
                        parent[nb] = (node, e)
                        q.append((nb, d + 1))
                        if nb in endpoint_ids:
                            min_d = 2 if (bridge_ids and nb in bridge_ids) else 1
                            if d + 1 >= min_d:
                                edges_list = (
                                    TermConnectionNetworkMixin._edges_from_parent(
                                        start, nb, parent
                                    )
                                )
                                if edges_list:
                                    _record(edges_list, start)

        # ── Pass 1: S → T + S → bridge ──────────────────────────────
        _bfs_pass(source_ids, target_ids | bridge_node_ids, bridge_ids=bridge_node_ids)

        # ── Pass 2: T → S + T → bridge ──────────────────────────────
        _bfs_pass(target_ids, source_ids | bridge_node_ids, bridge_ids=bridge_node_ids)

        return all_paths

    @staticmethod
    def _edges_from_parent(
        start: str, end: str, parent: dict[str, tuple[str, Edge | None]]
    ) -> list[Edge]:
        """Backtrack from end to start via parent chain, return edge list."""
        if end not in parent:
            return []
        edges: list[Edge] = []
        curr = end
        while curr != start:
            entry = parent.get(curr)
            if entry is None:
                return []
            prev, edge = entry
            if edge is None:
                return []
            edges.append(edge)
            curr = prev
        edges.reverse()
        return edges

    @staticmethod
    def _path_sig(start: str, edges: list[Edge]) -> tuple[str, ...]:
        """Build canonical node-id chain for path deduplication."""
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
        """Build connection_summary with empty one_sentence and writing_claim.

        Semantic fields are left empty per design — the writing Agent
        generates its own interpretations from the structured path data.
        """
        _ = source_nodes, target_nodes, top_paths
        return {"one_sentence": "", "writing_claim": ""}

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
