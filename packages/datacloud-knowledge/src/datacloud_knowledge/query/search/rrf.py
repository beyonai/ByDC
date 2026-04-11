"""RRF (Reciprocal Rank Fusion) 工具函数。

将多路召回结果按 RRF 公式融合为统一排序。
公式: score(d) = Σ 1 / (k + rank_i(d))  其中 k 为平滑常数（默认 60）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RRFCandidate:
    """RRF 融合后的单条结果。"""

    term_id: str
    term_name: str
    name_id: str
    term_type_code: str
    rrf_score: float


def rrf_fuse(
    ranked_lists: list[list[tuple[str, str, str, str]]],
    *,
    k: int = 60,
    top_n: int | None = None,
) -> list[RRFCandidate]:
    """对多个排序列表执行 RRF 融合。

    每个 ranked_list 中的元素为 ``(term_id, term_name, name_id, term_type_code)``，
    排在前面的 rank 更高。

    Args:
        ranked_lists: 多路召回的排序列表。
        k: RRF 平滑常数，默认 60。
        top_n: 截取融合后前 N 个结果，None 表示全部返回。

    Returns:
        按 rrf_score 降序排列的候选列表。
    """
    if not ranked_lists:
        return []

    # term_id -> 累积 rrf 分数
    score_map: dict[str, float] = {}
    # term_id -> (term_name, name_id, term_type_code)  取首次出现
    info_map: dict[str, tuple[str, str, str]] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            term_id, term_name, name_id, term_type_code = item
            score_map[term_id] = score_map.get(term_id, 0.0) + 1.0 / (k + rank)
            if term_id not in info_map:
                info_map[term_id] = (term_name, name_id, term_type_code)

    # 按 rrf_score 降序
    sorted_ids = sorted(score_map, key=lambda tid: score_map[tid], reverse=True)
    if top_n is not None:
        sorted_ids = sorted_ids[:top_n]

    return [
        RRFCandidate(
            term_id=tid,
            term_name=info_map[tid][0],
            name_id=info_map[tid][1],
            term_type_code=info_map[tid][2],
            rrf_score=score_map[tid],
        )
        for tid in sorted_ids
    ]
