"""Paradigm builder — 五段式解析、召回、paradigmList 构建。

从 byclaw_data.paradigm.builder 迁移核心逻辑到 knowledge SDK，
使 analyze_query_clarification 能在 SDK 内闭环完成全流程。

核心流程：
    五段式 dict → TypedKeywordState → typed_multi_recall → ParadigmResolutionState
    → build_paradigm_list / 判断 unresolved
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────

QUERY_TARGETS_KEY = "查询目标"
GROUP_BY_KEY = "分组条件"
FILTERS_KEY = "过滤条件"
ORDER_BY_KEY = "排序目标"
AGGREGATIONS_KEY = "统计函数"

_TIME_WORDS = frozenset(
    {
        "时间", "年份", "月份", "日期", "账期", "时间段", "季度",
        "time", "year", "month", "date", "billing period", "time period", "quarter",
    }
)

_QUANTIFIER_PATTERNS = (
    re.compile(r"^\s*(>=|<=|>|<|=)\s*(.+?)\s*$"),
    re.compile(r"^\s*(大于等于|不小于)\s*(.+?)\s*$"),
    re.compile(r"^\s*(小于等于|不大于)\s*(.+?)\s*$"),
    re.compile(r"^\s*(大于|高于|超过)\s*(.+?)\s*$"),
    re.compile(r"^\s*(小于|低于|少于)\s*(.+?)\s*$"),
    re.compile(r"^\s*(等于|为)\s*(.+?)\s*$"),
)

_PARADIGM_CONFIG: tuple[tuple[str, str, str], ...] = (
    ("1", "查询值", "select"),
    ("2", "分组条件", "groupBy"),
    ("3", "过滤条件", "filter"),
    ("4", "排序目标", "orderBy"),
    ("5", "统计函数", "aggregation"),
)


# ── 数据模型 ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class RecallCandidate:
    """知识召回候选项。"""

    term_id: str
    term_name: str
    term_type_code: str
    match_type: str
    confidence: float
    score: float
    name_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecallCandidate:
        return cls(
            term_id=str(data.get("term_id") or ""),
            term_name=str(data.get("term_name") or ""),
            term_type_code=str(data.get("term_type_code") or ""),
            match_type=str(data.get("match_type") or ""),
            confidence=float(data.get("confidence") or 0.0),
            score=float(data.get("score") or 0.0),
            name_id=str(data.get("name_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "term_id": self.term_id,
            "term_name": self.term_name,
            "term_type_code": self.term_type_code,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "score": self.score,
            "name_id": self.name_id,
        }


@dataclass(slots=True)
class TypedKeywordState:
    """五段式中的单个类型化关键词及其召回状态。"""

    item_id: str
    paradigm_id: str
    paradigm_name: str
    keyword: str
    kid: int
    ktype: str
    search_enabled: bool = True
    comparison: str = "eq"
    candidates: list[RecallCandidate] = field(default_factory=list)
    selected_term_id: str = ""
    user_supplied_text: str = ""

    @property
    def recall(self) -> list[str]:
        return [c.term_name for c in self.candidates]

    @property
    def interaction_type(self) -> str:
        if not self.search_enabled:
            return ""
        if self.user_supplied_text:
            return ""
        if self.selected_term_id or len(self.candidates) == 1:
            return ""
        if len(self.candidates) > 1:
            return "select"
        return "free_text"

    @property
    def resolved_keyword(self) -> str:
        if self.user_supplied_text:
            return self.user_supplied_text
        selected = self.selected_candidate
        if selected is not None:
            return selected.term_name
        return self.keyword

    @property
    def selected_candidate(self) -> RecallCandidate | None:
        if self.selected_term_id:
            for c in self.candidates:
                if c.term_id == self.selected_term_id:
                    return c
        if len(self.candidates) == 1:
            return self.candidates[0]
        return None

    @property
    def is_resolved(self) -> bool:
        return not self.interaction_type

    def apply_auto_resolution(self) -> None:
        if not self.search_enabled:
            return
        if len(self.candidates) == 1:
            self.selected_term_id = self.candidates[0].term_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "paradigm_id": self.paradigm_id,
            "paradigm_name": self.paradigm_name,
            "keyword": self.keyword,
            "kid": self.kid,
            "ktype": self.ktype,
            "search_enabled": self.search_enabled,
            "comparison": self.comparison,
            "candidates": [c.to_dict() for c in self.candidates],
            "selected_term_id": self.selected_term_id,
            "user_supplied_text": self.user_supplied_text,
        }


@dataclass(slots=True)
class ParadigmResolutionState:
    """Paradigm 解析状态：管理 typed items 的召回、解析和 paradigmList 构建。"""

    original_question: str
    structured_query: dict[str, Any]
    items: list[TypedKeywordState] = field(default_factory=list)
    knowledge_lookup_succeeded: bool = True
    dimension_value_hints: dict[str, list[Any]] = field(default_factory=dict)
    """keyword → list[DimValueHint]，从短语中识别出的维度值线索。"""

    def apply_auto_resolution(self) -> None:
        for item in self.items:
            item.apply_auto_resolution()

    def first_unresolved(self) -> TypedKeywordState | None:
        for item in self.items:
            if not item.is_resolved:
                return item
        return None

    def unresolved_items(self) -> list[TypedKeywordState]:
        return [item for item in self.items if not item.is_resolved]

    def build_paradigm_list(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[TypedKeywordState]] = {
            pid: [] for pid, _name, _ktype in _PARADIGM_CONFIG
        }
        for item in self.items:
            grouped.setdefault(item.paradigm_id, []).append(item)

        paradigms: list[dict[str, Any]] = []
        for paradigm_id, paradigm_name, paradigm_kind in _PARADIGM_CONFIG:
            items = grouped.get(paradigm_id, [])
            if paradigm_kind == "filter":
                paradigm_result = _build_filter_paradigm_result(items)
            else:
                paradigm_result = [
                    {
                        "keyword": item.resolved_keyword,
                        "recall": item.recall,
                        "kid": item.kid,
                        "ktype": item.ktype,
                    }
                    for item in items
                ]
            paradigms.append({
                "paradigmId": paradigm_id,
                "paradigmName": paradigm_name,
                "paradigmResult": paradigm_result,
            })
        return paradigms

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_question": self.original_question,
            "structured_query": self.structured_query,
            "items": [item.to_dict() for item in self.items],
            "knowledge_lookup_succeeded": self.knowledge_lookup_succeeded,
        }


# ── 公共 API ─────────────────────────────────────────────────────────


def build_paradigm_resolution_state(
    *,
    original_question: str,
    structured_query: dict[str, Any],
) -> ParadigmResolutionState:
    """从五段式构建 paradigm 解析状态（含召回）。

    Args:
        original_question: 用户原始查询。
        structured_query: 五段式 dict（key 为中文：查询目标/分组条件/…）。

    Returns:
        填充了召回候选的 ParadigmResolutionState。
    """
    normalized = {str(k): v for k, v in structured_query.items()}
    state = ParadigmResolutionState(
        original_question=original_question,
        structured_query=normalized,
        items=_build_typed_items(normalized),
    )
    logger.debug(
        "[paradigm_builder] 五段式解析: items=%d, searchable=%d, details=[%s]",
        len(state.items),
        sum(1 for it in state.items if it.search_enabled),
        ", ".join(
            f"{it.ktype}:{it.keyword!r}(search={it.search_enabled})"
            for it in state.items
        ),
    )
    state.knowledge_lookup_succeeded = _populate_recall_candidates(state)
    _enrich_dimension_value_hints(state)
    state.apply_auto_resolution()
    _log_resolution_summary(state)
    return state


def five_stage_keys_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """将 natquery_to_five_stage 输出的英文 key 转为中文 key（paradigm builder 要求）。"""
    return {
        QUERY_TARGETS_KEY: raw.get("query_target", []),
        GROUP_BY_KEY: raw.get("group_by", []),
        FILTERS_KEY: raw.get("filter_condition", {}),
        ORDER_BY_KEY: raw.get("order_by", []),
        AGGREGATIONS_KEY: raw.get("agg_function", []),
    }


# ── 内部实现 ─────────────────────────────────────────────────────────


def _build_typed_items(structured_query: dict[str, Any]) -> list[TypedKeywordState]:
    items: list[TypedKeywordState] = []

    for index, keyword in enumerate(structured_query.get(QUERY_TARGETS_KEY, []), start=1):
        items.append(TypedKeywordState(
            item_id=f"select-{index}",
            paradigm_id="1",
            paradigm_name="查询值",
            keyword=str(keyword),
            kid=index,
            ktype="select",
            search_enabled=not _is_time_word(str(keyword)),
        ))

    for index, keyword in enumerate(structured_query.get(GROUP_BY_KEY, []), start=1):
        items.append(TypedKeywordState(
            item_id=f"groupBy-{index}",
            paradigm_id="2",
            paradigm_name="分组条件",
            keyword=str(keyword),
            kid=index,
            ktype="groupBy",
            search_enabled=not _is_time_word(str(keyword)),
        ))

    filter_kid = 0
    filters = structured_query.get(FILTERS_KEY, {})
    if isinstance(filters, dict):
        for field_keyword, raw_values in filters.items():
            values = raw_values if isinstance(raw_values, list) and raw_values else [""]
            for raw_value in values:
                filter_kid += 1
                comparison, normalized_value = _normalize_filter_value(str(raw_value))
                items.append(TypedKeywordState(
                    item_id=f"whereKey-{filter_kid}",
                    paradigm_id="3",
                    paradigm_name="过滤条件",
                    keyword=str(field_keyword),
                    kid=filter_kid,
                    ktype="whereKey",
                    search_enabled=True,  # 字段名总是召回，需要解析到真实 schema
                    comparison=comparison,
                ))
                items.append(TypedKeywordState(
                    item_id=f"whereValue-{filter_kid}",
                    paradigm_id="3",
                    paradigm_name="过滤条件",
                    keyword=normalized_value,
                    kid=filter_kid,
                    ktype="whereValue",
                    search_enabled=not _should_skip_where_value_recall(
                        str(raw_value), normalized_value
                    ),
                    comparison=comparison,
                ))

    for index, keyword in enumerate(structured_query.get(ORDER_BY_KEY, []), start=1):
        items.append(TypedKeywordState(
            item_id=f"orderBy-{index}",
            paradigm_id="4",
            paradigm_name="排序目标",
            keyword=str(keyword),
            kid=index,
            ktype="orderBy",
            search_enabled=not _is_time_word(str(keyword)),
        ))

    for index, keyword in enumerate(structured_query.get(AGGREGATIONS_KEY, []), start=1):
        items.append(TypedKeywordState(
            item_id=f"aggregation-{index}",
            paradigm_id="5",
            paradigm_name="统计函数",
            keyword=str(keyword),
            kid=index,
            ktype="aggregation",
            search_enabled=False,
        ))

    return items


def _populate_recall_candidates(state: ParadigmResolutionState) -> bool:
    """对 typed items 执行知识召回，填充候选项。"""
    searchable = [
        item for item in state.items if item.search_enabled and item.keyword.strip()
    ]
    if not searchable:
        for item in state.items:
            item.candidates = []
        return True

    _t0 = time.monotonic()
    try:
        candidates_map = _search_typed_candidates(searchable)
        logger.info(
            "[paradigm_builder] recall: %.3fs items=%d",
            time.monotonic() - _t0,
            len(searchable),
        )
    except Exception:
        logger.exception("[paradigm_builder] 召回失败")
        for item in state.items:
            item.candidates = []
        return False

    for item in state.items:
        if not item.search_enabled:
            item.candidates = []
            continue
        map_key = f"{item.ktype}:{item.keyword}"
        raw_candidates = candidates_map.get(map_key, [])
        item.candidates = [
            RecallCandidate.from_dict(c)
            for c in raw_candidates
            if isinstance(c, dict)
        ]
        if item.candidates:
            top_names = [c.term_name for c in item.candidates[:3]]
            logger.debug(
                "[paradigm_builder] recall %s -> %d 候选: %s%s",
                map_key,
                len(item.candidates),
                top_names,
                "..." if len(item.candidates) > 3 else "",
            )
        else:
            logger.debug("[paradigm_builder] recall %s -> 0 候选", map_key)
    logger.info(
        "[paradigm_builder] recall total: %.3fs",
        time.monotonic() - _t0,
    )
    return True


def _search_typed_candidates(
    items: Sequence[TypedKeywordState],
) -> dict[str, list[dict[str, Any]]]:
    """调用 typed_multi_recall_with_session 执行分类型多路召回。"""
    from .service import typed_multi_recall_with_session

    items_list: list[Any] = list(items)
    return typed_multi_recall_with_session(items_list, top_k=5)


def _build_filter_paradigm_result(items: list[TypedKeywordState]) -> list[dict[str, Any]]:
    grouped: dict[int, list[TypedKeywordState]] = {}
    for item in items:
        grouped.setdefault(item.kid, []).append(item)

    result: list[dict[str, Any]] = []
    for kid in sorted(grouped):
        pair = grouped[kid]
        key_item = next((i for i in pair if i.ktype == "whereKey"), None)
        value_item = next((i for i in pair if i.ktype == "whereValue"), None)
        if key_item is None or value_item is None:
            continue
        result.append({
            "type": "predicate",
            "field": key_item.resolved_keyword,
            "fieldRecall": key_item.recall,
            "comparison": value_item.comparison,
            "value": value_item.resolved_keyword,
            "valueRecall": value_item.recall,
        })
    return result


# ── 辅助函数 ─────────────────────────────────────────────────────────


def _is_time_word(value: str) -> bool:
    """判断是否为时间相关的字段名（如"时间"、"年份"）。

    注意：仅用于 SELECT/GROUP BY/ORDER BY 的字段名判断。
    WHERE value 的时间判断请用 _is_time_value。
    """
    return value.strip().lower() in _TIME_WORDS


_TIME_VALUE_PATTERNS = (
    re.compile(r"^\d{6,8}$"),                                       # 202602, 20260201
    re.compile(r"^\d{4}[-/年]\d{1,2}[-/月]?(\d{1,2}日?)?$"),       # 2026-02, 2026年2月
    re.compile(r"^(第?[一二三四1-4]季度|[上下]半年|全年)$"),          # 第二季度, 上半年
    re.compile(r"^\d{4}年?$"),                                      # 2026, 2026年
)


def _is_time_value(value: str) -> bool:
    """判断 WHERE value 是否为时间值（不需要召回）。"""
    v = value.strip()
    if not v:
        return False
    return any(p.match(v) for p in _TIME_VALUE_PATTERNS)


def _is_numeric_expression(value: str) -> bool:
    """剥离运算符和单位后，判断是否为纯数值表达（不需要召回）。

    例：">5000万" → 剥离">"和"万" → "5000" → 纯数字 → True
    例："高风险" → 剥离后 "高风险" → 非数字 → False
    """
    cleaned = re.sub(
        r"[><=≥≤]|大于|小于|等于|超过|低于|高于|不[大小]于|以[上下]|多于|少于",
        "",
        value,
    )
    cleaned = cleaned.strip()
    if not cleaned:
        return False
    cleaned = re.sub(r"[万亿元%千百个件人户家次份]", "", cleaned)
    return bool(re.match(r"^[\d.]+$", cleaned.strip()))


def _normalize_filter_value(raw_value: str) -> tuple[str, str]:
    value = raw_value.strip()
    if not value:
        return "eq", ""
    for pattern in _QUANTIFIER_PATTERNS:
        match = pattern.match(value)
        if match is None:
            continue
        operator = match.group(1)
        normalized = match.group(2).strip()
        return _map_operator(operator), normalized
    return "eq", value


def _map_operator(operator: str) -> str:
    mapping = {
        ">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq",
        "大于": "gt", "高于": "gt", "超过": "gt",
        "大于等于": "gte", "不小于": "gte",
        "小于": "lt", "低于": "lt", "少于": "lt",
        "小于等于": "lte", "不大于": "lte",
        "等于": "eq", "为": "eq",
    }
    return mapping.get(operator, "eq")


def _should_skip_where_value_recall(raw_value: str, normalized_value: str) -> bool:
    """判断 WHERE value 是否应跳过召回。

    跳过条件：
    - 时间值（如 "202602"、"2026年2月"、"上半年"）
    - 纯数值表达式（如 ">5000万"、"低于6%"）
    """
    return _is_time_value(normalized_value) or _is_numeric_expression(raw_value)


def _log_resolution_summary(state: ParadigmResolutionState) -> None:
    """记录自动解析摘要：哪些已解析、哪些需要交互。"""
    resolved = []
    unresolved = []
    skipped = []
    for item in state.items:
        if not item.search_enabled:
            skipped.append(f"{item.ktype}:{item.keyword!r}")
        elif item.is_resolved:
            selected = item.selected_candidate
            label = selected.term_name if selected else item.keyword
            resolved.append(f"{item.ktype}:{item.keyword!r}->{label!r}")
        else:
            unresolved.append(
                f"{item.ktype}:{item.keyword!r}({len(item.candidates)}候选)"
            )
    logger.debug(
        "[paradigm_builder] 解析摘要: resolved=%d unresolved=%d skipped=%d",
        len(resolved),
        len(unresolved),
        len(skipped),
    )
    if resolved:
        logger.debug("[paradigm_builder]   resolved: %s", resolved)
    if unresolved:
        logger.debug("[paradigm_builder]   unresolved: %s", unresolved)
    if skipped:
        logger.debug("[paradigm_builder]   skipped: %s", skipped)


def _enrich_dimension_value_hints(state: ParadigmResolutionState) -> None:
    """对 select/groupBy 的关键词做维度值子词匹配，结果写入 state.dimension_value_hints。"""
    try:
        from .dimension_values import DimensionValueResolver  # noqa: PLC0415

        resolver = DimensionValueResolver.get_instance()
    except Exception:
        logger.debug("[paradigm_builder] DimensionValueResolver 不可用，跳过维度值识别")
        return

    enrichable_ktypes = {"select", "groupBy"}
    for item in state.items:
        if item.ktype not in enrichable_ktypes or not item.search_enabled:
            continue
        hints = resolver.match_keyword(item.keyword)
        if hints:
            state.dimension_value_hints[item.keyword] = hints
            logger.debug(
                "[paradigm_builder] 维度值识别 %r -> %s",
                item.keyword,
                [(h.matched_span, h.matched_value, h.dimension_prop) for h in hints],
            )
