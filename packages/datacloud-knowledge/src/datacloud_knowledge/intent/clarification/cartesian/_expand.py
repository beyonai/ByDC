"""Cartesian product expansion for complex_conditions.

Expands unconfirmed condition-term candidates via Cartesian product
(max 20 combinations), and applies sorted replacement by sentence span.
"""

from __future__ import annotations

import itertools
import logging

from datacloud_knowledge.i18n import get_annotation_format
from datacloud_knowledge.intent.clarification.models import ConditionTermMapping, ConfirmedCondition

logger = logging.getLogger(__name__)

MAX_COMBINATIONS = 20

# 合法运算符候选（与 WhereClause.op 一致）
_ALL_COMPARISON_OPS: list[str] = ["eq", "gt", "lt", "gte", "lte", "in", "between"]

# op 值标准化映射
_OP_NORMALIZE: dict[str, str] = {
    "=": "eq",
    "==": "eq",
    "eq": "eq",
    ">": "gt",
    "gt": "gt",
    "<": "lt",
    "lt": "lt",
    ">=": "gte",
    "gte": "gte",
    "<=": "lte",
    "lte": "lte",
    "in": "in",
    "IN": "in",
    "between": "between",
    "BETWEEN": "between",
}


def _normalize_op(raw_op: str) -> str:
    """将各种 op 表示标准化为前端 key。"""
    return _OP_NORMALIZE.get(raw_op.strip(), "eq")


def _build_comparison_recall(current_op: str) -> list[str]:
    """构建运算符候选列表，当前 op 排第一。"""
    result = [current_op]
    for op in _ALL_COMPARISON_OPS:
        if op != current_op:
            result.append(op)
    return result


def _fix_term_positions(
    sentence: str,
    mappings: list[ConditionTermMapping],
) -> None:
    """校正 LLM 返回的 start/end 位置。

    策略：
    - 术语在句子中只出现一次 → 直接 str.find，忽略 LLM 给的位置（LLM 偏差可能很大）
    - 术语出现多次 → 以 LLM start 为锚点 ±RADIUS 搜索，用位置消歧
    """
    used_positions: set[int] = set()
    for tm in mappings:
        term = tm.original_term
        term_len = len(term)
        best_pos: int | None = None

        # 统计术语在句子中出现的所有位置
        occurrences: list[int] = []
        search_start = 0
        while True:
            idx = sentence.find(term, search_start)
            if idx == -1:
                break
            occurrences.append(idx)
            search_start = idx + 1

        if len(occurrences) == 1:
            # 唯一出现 → 直接采信，不看 LLM 位置
            best_pos = occurrences[0]
        elif len(occurrences) > 1:
            # 多次出现 → 以 LLM start 为锚点，选最近且未占用的
            for occ in sorted(occurrences, key=lambda p: abs(p - tm.start)):
                if occ not in used_positions:
                    best_pos = occ
                    break
        # occurrences 为空 → best_pos 保持 None（术语不在句子中）

        if best_pos is not None and (
            best_pos != tm.start or best_pos + term_len != tm.end
        ):
            logger.debug(
                "[cartesian] 位置校正: '%s' (%d,%d) → (%d,%d)",
                term,
                tm.start,
                tm.end,
                best_pos,
                best_pos + term_len,
            )
            tm.start = best_pos
            tm.end = best_pos + term_len
            used_positions.add(best_pos)
        else:
            used_positions.add(tm.start)


# ── 笛卡尔积展开 ─────────────────────────────────────────────────────


def truncate_candidates(
    unconfirmed: list[ConditionTermMapping],
    max_combinations: int = MAX_COMBINATIONS,
) -> list[list[str]]:
    """按候选排名截断，确保笛卡尔积 ≤ max_combinations。

    从候选最多的术语开始，逐步裁剪末尾候选。

    Args:
        unconfirmed: 未确定的术语映射列表（confirmed is None）。
        max_combinations: 组合上限。

    Returns:
        每个术语的截断后候选列表。
    """
    if not unconfirmed:
        return []

    candidate_lists = [tm.candidates[:] for tm in unconfirmed]

    # 逐步裁剪，直到积 ≤ max_combinations
    while True:
        product = 1
        for cl in candidate_lists:
            product *= max(len(cl), 1)
        if product <= max_combinations:
            break

        # 找候选最多的术语，裁剪末尾
        max_idx = max(
            range(len(candidate_lists)), key=lambda i: len(candidate_lists[i])
        )
        if len(candidate_lists[max_idx]) <= 1:
            break  # 无法再裁剪
        candidate_lists[max_idx].pop()

    return candidate_lists


def expand_condition_cartesian(
    condition: ConfirmedCondition,
    max_combinations: int = MAX_COMBINATIONS,
    *,
    language: str = "zh_CN",
) -> list[str]:
    """对单条 complex_condition 做笛卡尔积展开。

    已确定术语：替换为 "原词（确认词）"，不参与组合。
    未确定术语：candidates 参与笛卡尔积。
    全部确定 → 返回单个句子（仍加括号注释）。

    Args:
        condition: LLM 确认后的单条 condition。
        max_combinations: 组合上限。

    Returns:
        展开后的句子列表。
    """
    sentence = condition.original_sentence
    if not condition.term_mappings:
        return [sentence]

    # 分离已确定 / 未确定
    confirmed_mappings: list[ConditionTermMapping] = []
    unconfirmed_mappings: list[ConditionTermMapping] = []
    for tm in condition.term_mappings:
        if tm.confirmed is not None:
            confirmed_mappings.append(tm)
        elif tm.candidates:
            unconfirmed_mappings.append(tm)

    # 校正 LLM 返回的 start/end（LLM 数字符位置常有 ±1~2 偏差）
    _fix_term_positions(sentence, confirmed_mappings)
    _fix_term_positions(sentence, unconfirmed_mappings)

    # 截断未确定术语的候选
    if unconfirmed_mappings:
        truncated = truncate_candidates(unconfirmed_mappings, max_combinations)
    else:
        truncated = []

    # 构建笛卡尔积
    combos = (
        list(itertools.product(*truncated)) if truncated else [()]
    )  # 全部确定，单个组合

    results: list[str] = []
    for combo in combos:
        result = _apply_replacements(
            sentence, confirmed_mappings, unconfirmed_mappings, combo, language=language
        )
        results.append(result)

    return results


def _apply_replacements(
    sentence: str,
    confirmed: list[ConditionTermMapping],
    unconfirmed: list[ConditionTermMapping],
    combo: tuple[str, ...],
    *,
    language: str = "zh_CN",
) -> str:
    """按 start/end 位置替换术语，生成带括号注释的句子。"""
    fmt = get_annotation_format(language)
    # 合并所有替换，按 start 降序排列（从后往前替换，避免位移）
    replacements: list[tuple[int, int, str, str]] = []

    for tm in confirmed:
        replacements.append((tm.start, tm.end, tm.original_term, tm.confirmed or ""))

    for i, tm in enumerate(unconfirmed):
        if i < len(combo):
            replacements.append((tm.start, tm.end, tm.original_term, combo[i]))

    # 按 start 降序
    replacements.sort(key=lambda r: r[0], reverse=True)

    result = sentence
    for start, end, _original, replacement in replacements:
        annotated = fmt.format(text=replacement)
        result = result[:start] + annotated + result[end:]

    return result
