"""澄清模块编排层 — 4 个公共函数入口。

公共 API：
    - analyze_query_clarification_query
    - analyze_query_clarification_compute
    - format_clarification_query
    - format_clarification_compute
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from datacloud_knowledge.intent.llm_utils import EventEmitter
from datacloud_knowledge.intent.types import ClarificationResult

from .cartesian import build_paradigm_list, serialize_knowledge_meta, serialize_paradigm_payload
from .confirm import format_recall_context, llm_confirm_structured
from .extract import (
    ExtractedTerm,
    extract_terms_complex_conditions,
    extract_terms_compute,
    extract_terms_query,
)
from .format import format_clarification_compute as _format_compute
from .format import format_clarification_query as _format_query

logger = logging.getLogger(__name__)


# ── 分析入口 ─────────────────────────────────────────────────────────


def analyze_query_clarification_query(
    query: str,
    ontology_code: str,
    structured_query: dict[str, Any],
    on_event: Callable[[Any], None] | None = None,
) -> ClarificationResult:
    """分析 StructuredQuery 是否需要用户澄清。

    Args:
        query: 用户原始自然语言查询。
        ontology_code: 本体编码（预留，暂不过滤）。
        structured_query: StructuredQuery 的 dict 表示。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        ClarificationResult。
    """
    # TODO(ontology): 按 ontology_code 过滤召回候选的术语范围
    _ = ontology_code

    emit = EventEmitter(on_event)
    complex_conditions: list[str] = structured_query.get("complex_conditions", [])

    # ── Step 1: 术语提取 ──
    with emit.step("术语提取", "extract_terms", {"mode": "query"}):
        main_terms = extract_terms_query(structured_query)
        cc_terms = (
            extract_terms_complex_conditions(complex_conditions) if complex_conditions else []
        )
        all_terms = main_terms + cc_terms
        emit.result({"main": len(main_terms), "complex_conditions": len(cc_terms)})

    logger.info(
        "[clarification] Step1 术语提取: main=%d, cc=%d",
        len(main_terms),
        len(cc_terms),
    )

    # ── Step 2: 统一召回 ──
    with emit.step("知识召回", "knowledge_recall"):
        recall_map = _unified_recall(all_terms)
        emit.result({"terms": len(all_terms), "recalled": sum(1 for v in recall_map.values() if v)})

    # ── Step 3: LLM 确认 ──
    recall_context = format_recall_context(
        all_terms,
        recall_map,
        complex_conditions=complex_conditions,
    )
    with emit.step("查询确认", "llm_confirm"):
        confirmed = llm_confirm_structured(
            query=query,
            structured_input=structured_query,
            recall_context=recall_context,
            mode="query",
            on_event=on_event,
        )
        if confirmed is None:
            logger.warning("[clarification] LLM 确认失败，返回原始查询")
            emit.error("LLM 确认失败")
            return ClarificationResult(query=query)
        emit.result({"needs_clarification": confirmed.needs_clarification})

    # ── Step 4: 构建 paradigmList ──
    with emit.step("结果生成", "build_paradigm_list"):
        paradigm_list, meta = build_paradigm_list(
            confirmed,
            all_terms,
            recall_map,
            complex_conditions=complex_conditions,
            original_structured=structured_query,
        )
        form_payload = serialize_paradigm_payload(paradigm_list)
        knowledge_payload = serialize_knowledge_meta(meta)
        emit.result(form_payload)

    if confirmed.needs_clarification:
        logger.info("[clarification] 需要澄清: %d 项", len(confirmed.clarify_items))
        return ClarificationResult(
            query=query,
            needs_clarification=True,
            form=form_payload,
            knowledge=knowledge_payload,
        )

    logger.info("[clarification] 无需澄清")
    return ClarificationResult(
        query=query,
        needs_clarification=False,
        form=form_payload,
        knowledge=knowledge_payload,
    )


def analyze_query_clarification_compute(
    query: str,
    ontology_code: str,
    structured_compute: dict[str, Any],
    on_event: Callable[[Any], None] | None = None,
) -> ClarificationResult:
    """分析 StructuredCompute 是否需要用户澄清。

    Args:
        query: 用户原始自然语言查询。
        ontology_code: 本体编码（预留，暂不过滤）。
        structured_compute: StructuredCompute 的 dict 表示。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        ClarificationResult。
    """
    # TODO(ontology): 按 ontology_code 过滤召回候选的术语范围
    _ = ontology_code

    emit = EventEmitter(on_event)
    complex_conditions: list[str] = structured_compute.get("complex_conditions", [])

    # ── Step 1: 术语提取 ──
    with emit.step("术语提取", "extract_terms", {"mode": "compute"}):
        main_terms = extract_terms_compute(structured_compute)
        cc_terms = (
            extract_terms_complex_conditions(complex_conditions) if complex_conditions else []
        )
        all_terms = main_terms + cc_terms
        emit.result({"main": len(main_terms), "complex_conditions": len(cc_terms)})

    logger.info(
        "[clarification] Step1 术语提取: main=%d, cc=%d",
        len(main_terms),
        len(cc_terms),
    )

    # ── Step 2: 统一召回 ──
    with emit.step("知识召回", "knowledge_recall"):
        recall_map = _unified_recall(all_terms)
        emit.result({"terms": len(all_terms), "recalled": sum(1 for v in recall_map.values() if v)})

    # ── Step 3: LLM 确认 ──
    recall_context = format_recall_context(
        all_terms,
        recall_map,
        complex_conditions=complex_conditions,
    )
    with emit.step("查询确认", "llm_confirm"):
        confirmed = llm_confirm_structured(
            query=query,
            structured_input=structured_compute,
            recall_context=recall_context,
            mode="compute",
            on_event=on_event,
        )
        if confirmed is None:
            logger.warning("[clarification] LLM 确认失败，返回原始查询")
            emit.error("LLM 确认失败")
            return ClarificationResult(query=query)
        emit.result({"needs_clarification": confirmed.needs_clarification})

    # ── Step 4: 构建 paradigmList ──
    with emit.step("结果生成", "build_paradigm_list"):
        paradigm_list, meta = build_paradigm_list(
            confirmed,
            all_terms,
            recall_map,
            complex_conditions=complex_conditions,
            original_structured=structured_compute,
        )
        form_payload = serialize_paradigm_payload(paradigm_list)
        knowledge_payload = serialize_knowledge_meta(meta)
        emit.result(form_payload)

    if confirmed.needs_clarification:
        logger.info("[clarification] 需要澄清: %d 项", len(confirmed.clarify_items))
        return ClarificationResult(
            query=query,
            needs_clarification=True,
            form=form_payload,
            knowledge=knowledge_payload,
        )

    logger.info("[clarification] 无需澄清")
    return ClarificationResult(
        query=query,
        needs_clarification=False,
        form=form_payload,
        knowledge=knowledge_payload,
    )


# ── 格式化入口 ───────────────────────────────────────────────────────


def format_clarification_query(
    query: str,
    structured_query: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredQuery。

    Args:
        query: 用户原始查询。
        structured_query: 原始 StructuredQuery dict。
        form: 前端回传的 JSON（含 paradigmList）。
        knowledge: 内部元数据 JSON。

    Returns:
        确定的 StructuredQuery dict。
    """
    return _format_query(query, structured_query, form, knowledge)


def format_clarification_compute(
    query: str,
    structured_compute: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredCompute。

    Args:
        query: 用户原始查询。
        structured_compute: 原始 StructuredCompute dict。
        form: 前端回传的 JSON（含 paradigmList）。
        knowledge: 内部元数据 JSON。

    Returns:
        确定的 StructuredCompute dict。
    """
    return _format_compute(query, structured_compute, form, knowledge)


# ── 内部辅助 ─────────────────────────────────────────────────────────


def _unified_recall(
    terms: list[ExtractedTerm],
) -> dict[str, list[dict[str, Any]]]:
    """对所有术语执行统一召回。

    将 ExtractedTerm 转为 TypedKeywordState 协议对象，
    调用 typed_multi_recall_with_session 执行召回。
    vector_only 术语（英文标识符如 stat_date）只走向量召回路径。

    Returns:
        dict["ktype:raw_text", list[CandidateDict]]。
    """
    from datacloud_knowledge.intent.service import typed_multi_recall_with_session

    # 去重：相同 ktype + raw_text 只召回一次
    seen: set[str] = set()
    normal_items: list[_RecallItem] = []
    vector_only_items: list[_RecallItem] = []
    for term in terms:
        if not term.search_enabled:
            continue
        key = f"{term.ktype}:{term.raw_text}"
        if key in seen:
            continue
        seen.add(key)
        item = _RecallItem(
            keyword=term.raw_text,
            ktype=term.ktype,
            search_enabled=True,
        )
        if term.vector_only:
            vector_only_items.append(item)
        else:
            normal_items.append(item)

    result: dict[str, list[dict[str, Any]]] = {}

    # 常规术语：走全部 4 路召回（BM25 + Jieba + Substring + Vector）
    if normal_items:
        result.update(typed_multi_recall_with_session(normal_items, top_k=5))

    # 英文标识符：只走向量召回（BM25/子串匹配对英文→中文无意义）
    if vector_only_items:
        result.update(_vector_only_recall(vector_only_items, top_k=5))

    return result


def _vector_only_recall(
    items: list[_RecallItem],
    *,
    top_k: int,
) -> dict[str, list[dict[str, Any]]]:
    """对英文标识符术语只执行向量召回。

    英文编码（如 stat_date）无法通过 BM25/子串匹配命中中文术语名，
    但向量语义检索可以将 "stat_date" 匹配到 "统计日期"。
    """
    from datacloud_knowledge.intent.batch_recall import RecallRequest, _batch_vector
    from datacloud_knowledge.intent.typed_recall import (
        KTYPE_CATEGORY_MAP,
        _load_type_codes_by_category,
        _shape_candidates,
    )
    from datacloud_knowledge.knowledge_search.db.connection import get_session

    # 构建 RecallRequest（需要 type_filter）
    with get_session() as session:
        category_cache: dict[frozenset[int], set[str]] = {}
        requests: list[RecallRequest] = []
        for item in items:
            allowed_categories = KTYPE_CATEGORY_MAP.get(item.ktype)
            if allowed_categories is None:
                type_filter: set[str] | None = None
            else:
                cat_key = frozenset(allowed_categories)
                if cat_key not in category_cache:
                    category_cache[cat_key] = _load_type_codes_by_category(
                        session, allowed_categories
                    )
                type_filter = category_cache[cat_key]
                if not type_filter:
                    continue

            frozen_filter = frozenset(type_filter) if type_filter is not None else None
            requests.append(
                RecallRequest(
                    map_key=f"{item.ktype}:{item.keyword}",
                    keyword=item.keyword,
                    ktype=item.ktype,
                    type_filter=frozen_filter,
                    is_per_type=False,
                    per_type_limit=0,
                )
            )

    if not requests:
        return {}

    from datacloud_knowledge.intent.batch_recall import PreparedBatch

    batch = PreparedBatch(
        requests=tuple(requests),
        normal_requests=tuple(requests),
        per_type_requests=(),
    )

    # 只走向量路径
    vector_hits = _batch_vector(batch, top_k=top_k)

    # 整形为 CandidateDict
    from datacloud_knowledge.query.search.rrf import rrf_fuse

    result: dict[str, list[dict[str, Any]]] = {}
    for req in requests:
        hits = vector_hits.get(req.map_key, [])
        if hits:
            fused = rrf_fuse([hits], k=60, top_n=top_k * 3)
            candidates = _shape_candidates(fused, req.type_filter, top_k=top_k)
        else:
            candidates = []
        result[req.map_key] = candidates
        if candidates:
            logger.info(
                "[clarification] vector_only recall %s -> %d 候选, top=%s",
                req.map_key,
                len(candidates),
                candidates[0]["term_name"] if candidates else "",
            )

    return result


class _RecallItem:
    """轻量 TypedKeywordState 协议实现，用于传入 typed_multi_recall_with_session。"""

    __slots__ = ("keyword", "ktype", "search_enabled")

    def __init__(self, keyword: str, ktype: str, search_enabled: bool) -> None:
        self.keyword = keyword
        self.ktype = ktype
        self.search_enabled = search_enabled
