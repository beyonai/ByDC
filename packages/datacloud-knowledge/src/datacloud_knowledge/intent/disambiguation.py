"""多维消歧 — 算法 C。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.types import ShortestPathNode

from .types import (
    DisambiguationResult,
    MatchCandidate,
    MatchResult,
    ShortestPathGraphEdge,
    ShortestPathGraphNode,
    ShortestPathTreeNode,
    ShortestPathTreeResult,
)

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

_CONFIDENCE_GAP_THRESHOLD = 0.15
_CONFIRMED_CONFIDENCE_THRESHOLD = 0.95
_MAX_SCORE_BOOST = 0.25
_SCORE_WEIGHT = 0.5
_DEFAULT_MAX_BFS_DEPTH = 4


def disambiguate(
    match_result: MatchResult,
    session: Any,
) -> DisambiguationResult:
    """执行多维消歧。"""
    confirmed: dict[str, MatchCandidate] = {}
    ambiguous: dict[str, tuple[MatchCandidate, ...]] = {}
    mention_candidates = _merge_candidates(match_result)
    anchors: list[MatchCandidate] = []
    # 遍历每个 mention 的候选
    for mention_text, candidates in mention_candidates.items():
        if len(candidates) == 0:
            # 无候选，标记为歧义（完全未知）
            ambiguous[mention_text] = ()
            continue
        if len(candidates) == 1:
            candidate = candidates[0]
            if candidate.confidence >= _CONFIRMED_CONFIDENCE_THRESHOLD:
                confirmed[mention_text] = candidate
                anchors.append(candidate)
            else:
                ambiguous[mention_text] = candidates
            continue
        # 多候选：尝试消歧
        ranked = _score_weighted_rank(candidates)
        top1_score = _weighted_score(ranked[0])
        top2_score = _weighted_score(ranked[1])
        score_gap = top1_score - top2_score
        if score_gap > _CONFIDENCE_GAP_THRESHOLD:
            confirmed[mention_text] = ranked[0]
            anchors.append(ranked[0])
            continue
        # 图谱拓扑校验
        topology_winner = _topology_check(
            candidates=ranked,
            anchors=anchors,
            session=session,
        )
        if topology_winner is not None:
            confirmed[mention_text] = topology_winner
            anchors.append(topology_winner)
        else:
            ambiguous[mention_text] = tuple(ranked)
    return DisambiguationResult(
        confirmed=confirmed,
        ambiguous=ambiguous,
    )


def _score_weighted_rank(
    candidates: tuple[MatchCandidate, ...],
) -> list[MatchCandidate]:
    """按 score 加权置信度排序。

    final_score = confidence * (1 + score_boost)
    score_boost = min(score * 0.5, 0.25)
    """
    return sorted(
        candidates,
        key=lambda candidate: (_weighted_score(candidate), candidate.confidence, candidate.score),
        reverse=True,
    )


def _bfs_distance(
    source_term_id: str,
    target_term_id: str,
    session: Any,
    max_depth: int = 4,
) -> int | None:
    """计算 source 到 target 的最短 BFS 距离，不可达返回 None。

    委托 ``TermReader.get_bfs_distance``，原子 DB 操作在 adapter 内完成。
    ``session`` 参数保留兼容，当前未使用。
    """
    return create_reader().get_bfs_distance(
        source_term_id=source_term_id,
        target_term_id=target_term_id,
        max_depth=max_depth,
    )


def _topology_check(
    candidates: list[MatchCandidate],
    anchors: list[MatchCandidate],
    session: Any,
) -> MatchCandidate | None:
    """基于候选到 anchors 的最短距离进行拓扑判别。"""
    if not candidates or not anchors:
        return None

    distance_records: list[tuple[MatchCandidate, int]] = []

    for candidate in candidates:
        min_distance: int | None = None
        for anchor in anchors:
            distance = _bfs_distance(
                source_term_id=candidate.term_id,
                target_term_id=anchor.term_id,
                session=session,
                max_depth=_DEFAULT_MAX_BFS_DEPTH,
            )
            if distance is None:
                continue
            if min_distance is None or distance < min_distance:
                min_distance = distance

        if min_distance is not None:
            distance_records.append((candidate, min_distance))

    if not distance_records:
        return None

    distance_records.sort(key=lambda item: item[1])
    winner, winner_distance = distance_records[0]

    if len(distance_records) == 1:
        return winner

    second_distance = distance_records[1][1]
    if second_distance - winner_distance >= 1:
        return winner

    return None


def _merge_candidates(match_result: MatchResult) -> dict[str, tuple[MatchCandidate, ...]]:
    """合并 exact/fuzzy 候选，按 mention 聚合并按 term_id 去重。"""
    merged: dict[str, list[MatchCandidate]] = {}

    for mention, candidates in match_result.exact.items():
        merged.setdefault(mention, []).extend(candidates)

    for mention, candidates in match_result.fuzzy.items():
        merged.setdefault(mention, []).extend(candidates)

    deduplicated: dict[str, tuple[MatchCandidate, ...]] = {}
    for mention, cand_list in merged.items():
        by_term_id: dict[str, MatchCandidate] = {}
        for candidate in cand_list:
            existing = by_term_id.get(candidate.term_id)
            if existing is None or _weighted_score(candidate) > _weighted_score(existing):
                by_term_id[candidate.term_id] = candidate
        deduplicated[mention] = tuple(by_term_id.values())

    return deduplicated


def _weighted_score(candidate: MatchCandidate) -> float:
    """计算候选加权分数。"""
    score_boost = min(candidate.score * _SCORE_WEIGHT, _MAX_SCORE_BOOST)
    return candidate.confidence * (1 + score_boost)


def build_shortest_path_tree(
    *,
    target_term_id: str,
    source_term_type_codes: Sequence[str],
    max_depth: int = 6,
) -> ShortestPathTreeResult:
    """构建从限定类型根节点到目标术语的最短路径子图与树文本。

    数据库访问通过 ``create_reader().get_shortest_path_tree()`` 完成，
    不再需要外部传入 session。
    """
    normalized_type_codes = tuple(code.strip() for code in source_term_type_codes if code.strip())
    if not target_term_id.strip():
        msg = "target_term_id must not be blank"
        raise ValueError(msg)
    if not normalized_type_codes:
        msg = "source_term_type_codes must not be empty"
        raise ValueError(msg)
    if max_depth <= 0:
        msg = "max_depth must be positive"
        raise ValueError(msg)
    rows = create_reader().get_shortest_path_tree(
        target_term_id=target_term_id,
        source_term_type_codes=normalized_type_codes,
        max_depth=max_depth,
    )
    if not rows:
        return ShortestPathTreeResult(
            target_term_id=target_term_id,
            source_term_type_codes=normalized_type_codes,
            root_term_ids=(),
        )
    return _build_shortest_path_tree_result(
        target_term_id=target_term_id,
        source_term_type_codes=normalized_type_codes,
        rows=rows,
    )


def _build_shortest_path_tree_result(
    *,
    target_term_id: str,
    source_term_type_codes: tuple[str, ...],
    rows: Sequence[ShortestPathNode],
) -> ShortestPathTreeResult:
    """将最短路径查询结果转换为结构化结果。"""
    node_map: dict[str, ShortestPathGraphNode] = {}
    edge_map: dict[tuple[str, str, str], ShortestPathGraphEdge] = {}
    path_payloads: list[dict[str, Any]] = []

    for row in rows:
        path_term_ids = [str(value) for value in row.path_term_ids]
        path_term_names = [str(value) for value in row.path_term_names]
        path_term_type_codes = [str(value) for value in row.path_term_type_codes]
        path_term_desc_summaries = [
            str(value) if value is not None else "" for value in row.path_term_desc_summaries
        ]
        path_descriptions = [
            str(value) if value is not None else "" for value in row.path_descriptions
        ]
        path_relations = [str(value) for value in row.path_relations]

        for index, term_id in enumerate(path_term_ids):
            if term_id not in node_map:
                description = _merge_node_descriptions(
                    path_term_desc_summaries[index],
                    path_descriptions[index],
                )
                node_map[term_id] = ShortestPathGraphNode(
                    term_id=term_id,
                    term_name=path_term_names[index],
                    term_type_code=path_term_type_codes[index],
                    description=description,
                )
            if index == 0:
                continue
            edge_key = (path_term_ids[index - 1], term_id, path_relations[index - 1])
            edge_map.setdefault(
                edge_key,
                ShortestPathGraphEdge(
                    source_term_id=path_term_ids[index - 1],
                    target_term_id=term_id,
                    relation_name=path_relations[index - 1],
                ),
            )

        path_payloads.append(
            {
                "term_ids": path_term_ids,
                "relations": path_relations,
            }
        )

    roots = _build_tree_roots(node_map=node_map, path_payloads=path_payloads)
    tree_text = _render_shortest_path_tree_text(roots)
    ordered_nodes = tuple(
        sorted(node_map.values(), key=lambda item: (item.term_name, item.term_id))
    )
    ordered_edges = tuple(
        sorted(
            edge_map.values(),
            key=lambda item: (item.source_term_id, item.target_term_id, item.relation_name),
        )
    )

    return ShortestPathTreeResult(
        target_term_id=target_term_id,
        source_term_type_codes=source_term_type_codes,
        root_term_ids=tuple(root.term_id for root in roots),
        nodes=ordered_nodes,
        edges=ordered_edges,
        roots=roots,
        tree_text=tree_text,
    )


def _merge_node_descriptions(*parts: str) -> str | None:
    """合并多个描述来源，去空与去重。"""
    normalized_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = part.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_parts.append(normalized)
    if not normalized_parts:
        return None
    return "；".join(normalized_parts)


def _build_tree_roots(
    *,
    node_map: dict[str, ShortestPathGraphNode],
    path_payloads: Sequence[dict[str, Any]],
) -> tuple[ShortestPathTreeNode, ...]:
    """根据路径集合构建树根节点。"""

    def _build_branch(
        path_index_pairs: Sequence[tuple[int, str]], level: int = 0
    ) -> tuple[ShortestPathTreeNode, ...]:
        grouped: dict[str, list[int]] = {}
        for payload_index, term_id in path_index_pairs:
            grouped.setdefault(term_id, []).append(payload_index)

        branches: list[ShortestPathTreeNode] = []
        for term_id in sorted(grouped, key=lambda value: (node_map[value].term_name, value)):
            indices = grouped[term_id]
            child_pairs: list[tuple[int, str]] = []
            relation_from_parent = ""
            if level > 0:
                first_payload = path_payloads[indices[0]]
                relation_from_parent = str(first_payload["relations"][level - 1])
            for payload_index in indices:
                payload = path_payloads[payload_index]
                term_ids = payload["term_ids"]
                next_level = level + 1
                if next_level >= len(term_ids):
                    continue
                child_term_id = term_ids[next_level]
                child_pairs.append((payload_index, child_term_id))

            graph_node = node_map[term_id]
            branches.append(
                ShortestPathTreeNode(
                    term_id=graph_node.term_id,
                    term_name=graph_node.term_name,
                    term_type_code=graph_node.term_type_code,
                    description=graph_node.description,
                    relation_from_parent=relation_from_parent,
                    children=_build_branch(child_pairs, level + 1) if child_pairs else (),
                )
            )
        return tuple(branches)

    root_pairs = [(index, payload["term_ids"][0]) for index, payload in enumerate(path_payloads)]
    return _build_branch(root_pairs)


def _render_shortest_path_tree_text(roots: Sequence[ShortestPathTreeNode]) -> str:
    """将树节点渲染为目录树风格文本。"""
    lines: list[str] = []
    child_prefix = "    " if len(roots) == 1 else ""
    for index, root in enumerate(roots):
        lines.append(_format_tree_node_line(node=root, prefix="", is_last=index == len(roots) - 1))
        root_is_last = index == len(roots) - 1
        for child_index, child in enumerate(root.children):
            lines.extend(
                _render_tree_node_lines(
                    child,
                    prefix=child_prefix,
                    is_last=child_index == len(root.children) - 1,
                    display_is_last=root_is_last if len(roots) > 1 and not child_prefix else None,
                )
            )
    return "\n".join(lines)


def _render_tree_node_lines(
    node: ShortestPathTreeNode,
    *,
    prefix: str,
    is_last: bool,
    display_is_last: bool | None = None,
) -> list[str]:
    """递归渲染树节点。"""
    effective_is_last = is_last if display_is_last is None else display_is_last
    line = _format_tree_node_line(
        node=node,
        prefix=prefix,
        is_last=effective_is_last,
    )
    lines = [line]
    child_prefix = prefix + ("    " if effective_is_last else "│   ")
    for child_index, child in enumerate(node.children):
        lines.extend(
            _render_tree_node_lines(
                child,
                prefix=child_prefix,
                is_last=child_index == len(node.children) - 1,
                display_is_last=None,
            )
        )
    return lines


def _format_tree_node_line(
    *,
    node: ShortestPathTreeNode,
    prefix: str,
    is_last: bool,
) -> str:
    """格式化单个树节点行。"""
    connector = ""
    if prefix or node.relation_from_parent:
        connector = "└── "
    if (prefix or node.relation_from_parent) and not is_last:
        connector = "├── "
    relation_prefix = f"[{node.relation_from_parent}] " if node.relation_from_parent else ""
    base = f"{prefix}{connector}{relation_prefix}{node.term_name} [{node.term_type_code}]"
    description = (node.description or "").strip()
    return f"{base} - {description}" if description else base
