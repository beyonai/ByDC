"""多维消歧 — 算法 C。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from .types import DisambiguationResult, MatchCandidate, MatchResult

log = logging.getLogger(__name__)

_CONFIDENCE_GAP_THRESHOLD = 0.15
_CONFIRMED_CONFIDENCE_THRESHOLD = 0.95
_MAX_SCORE_BOOST = 0.25
_SCORE_WEIGHT = 0.5
_DEFAULT_MAX_BFS_DEPTH = 4


def disambiguate(
    match_result: MatchResult,
    session: Any,
    schema: str = "whale_datacloud",
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
            schema=schema,
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
    schema: str = "whale_datacloud",
    max_depth: int = 4,
) -> int | None:
    """计算 source 到 target 的最短 BFS 距离，不可达返回 None。"""
    if source_term_id == target_term_id:
        return 0

    if max_depth <= 0:
        return None

    if schema != "whale_datacloud":
        msg = "Only whale_datacloud schema is supported in disambiguation BFS query."
        raise ValueError(msg)

    sql = text(
        """
        WITH RECURSIVE bfs AS (
            SELECT
                :source_id::varchar AS current_id,
                0 AS depth,
                ARRAY[:source_id::varchar]::varchar[] AS path

            UNION ALL

            SELECT
                CASE
                    WHEN tr.source_term_id = b.current_id THEN tr.target_term_id
                    ELSE tr.source_term_id
                END,
                b.depth + 1,
                b.path || CASE
                    WHEN tr.source_term_id = b.current_id THEN tr.target_term_id
                    ELSE tr.source_term_id
                END
            FROM bfs b
            JOIN whale_datacloud.term_relation tr
                ON tr.source_term_id = b.current_id OR tr.target_term_id = b.current_id
            WHERE b.depth < :max_depth
              AND NOT (
                    CASE
                        WHEN tr.source_term_id = b.current_id THEN tr.target_term_id
                        ELSE tr.source_term_id
                    END
                ) = ANY(b.path)
        )
        SELECT depth
        FROM bfs
        WHERE current_id = :target_id
        ORDER BY depth
        LIMIT 1
        """
    )

    row = session.execute(
        sql,
        {
            "source_id": source_term_id,
            "target_id": target_term_id,
            "max_depth": max_depth,
        },
    ).fetchone()
    if row is None:
        return None

    return int(row[0])


def _topology_check(
    candidates: list[MatchCandidate],
    anchors: list[MatchCandidate],
    session: Any,
    schema: str = "whale_datacloud",
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
                schema=schema,
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
