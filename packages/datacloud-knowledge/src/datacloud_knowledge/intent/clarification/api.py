"""澄清模块编排层 — 澄清分析与格式化公共入口。

公共 API：
    - analyze_query_clarification
    - format_clarification_query
    - format_clarification_compute
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from datacloud_knowledge.intent.llm_utils import EventEmitter
from datacloud_knowledge.intent.types import ClarificationResult
from datacloud_knowledge.retrieval._recall import (
    build_scope_recall_layers as _build_scope_recall_layers,
)
from datacloud_knowledge.retrieval._recall import (
    unified_recall as _unified_recall,
)

from ._merge import (  # noqa: F401 — re-exported for backward compatibility
    _dedupe_condition_term_mappings,
    _MergeConfirmed,
    _TermResolutionHint,
)
from ._merge import (
    build_main_resolution_hints as _build_main_resolution_hints,
)
from ._merge import (
    merge_cc_resolution_hints as _merge_cc_resolution_hints,
)
from ._merge import (
    merge_pre_resolve_hints as _merge_pre_resolve_hints,
)
from ._merge import (
    merge_to_confirmed_compute as _merge_to_confirmed_compute,
)
from ._merge import (
    merge_to_confirmed_query as _merge_to_confirmed_query,
)
from ._merge import (
    normalize_cc_result_with_hints as _normalize_cc_result_with_hints,
)
from ._patch import (
    build_pre_resolved_input as _build_pre_resolved_input,
)
from ._pre_resolve import (
    pre_resolve_terms as _pre_resolve_terms,
)
from .cartesian import (
    build_paradigm_list,
    serialize_knowledge_meta,
    serialize_paradigm_payload,
)
from .confirm import (
    format_cc_confirm_context,
    format_main_confirm_context,
    llm_confirm_cc,
    llm_confirm_main,
)
from .extract import (
    ExtractedTerm,
    extract_terms_complex_conditions,
    extract_terms_compute,
    extract_terms_query,
)
from .format import format_clarification_compute as _format_compute
from .format import format_clarification_query as _format_query

logger = logging.getLogger(__name__)

ClarificationMode = Literal["query", "compute"]


# ── 分析入口 ─────────────────────────────────────────────────────────


def analyze_query_clarification(
    query: str,
    ontology_code: str,
    structured_input: dict[str, Any],
    *,
    mode: ClarificationMode,
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> ClarificationResult:
    """分析结构化查询或统计参数是否需要用户澄清。

    该函数是澄清分析的统一编排入口，负责把 StructuredQuery 与
    StructuredCompute 收敛到同一条处理链路：术语提取、字段预解析、知识召回、
    LLM 确认、结果合并、前端 paradigmList 生成。调用方通过 ``mode`` 指定输入
    结构类型，函数内部按模式选择对应的术语提取器和确认结果合并器。
    """
    extract_terms: Callable[[dict[str, Any]], list[ExtractedTerm]]
    merge_confirmed: _MergeConfirmed

    if mode == "query":
        extract_terms = extract_terms_query
        merge_confirmed = _merge_to_confirmed_query
    else:
        extract_terms = extract_terms_compute
        merge_confirmed = _merge_to_confirmed_compute

    emit = EventEmitter(on_event)
    complex_conditions: list[str] = structured_input.get("complex_conditions", [])

    # ── Step 1: 术语提取 ──
    with emit.step("术语提取", "extract_terms", {"mode": mode}):
        main_terms = extract_terms(structured_input)
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

    # ── Step 2: Pre-Resolve ──
    with emit.step("字段预解析", "pre_resolve"):
        pre = _pre_resolve_terms(main_terms, scope_code=ontology_code)
        pre_result = {
            "confirmed": len(pre.confirmed),
            "unresolved": len(pre.unresolved_terms),
        }
        if mode == "query":
            pre_result["value_constraints"] = len(pre.value_enum_map)
        emit.result(pre_result)

    with emit.step("条件字段预解析", "pre_resolve_cc"):
        cc_pre = _pre_resolve_terms(cc_terms, scope_code=ontology_code)
        emit.result(
            {
                "confirmed": len(cc_pre.confirmed),
                "unresolved": len(cc_pre.unresolved_terms),
            }
        )

    # ── Step 3: 定向召回 ──
    recall_terms = list(pre.unresolved_terms) + list(cc_pre.unresolved_terms)
    field_layers, value_layers = _build_scope_recall_layers(ontology_code, pre, cc_pre)
    use_field_layers = field_layers if len(field_layers) > 1 else None
    use_value_layers = value_layers if len(value_layers) > 1 else None
    with emit.step("知识召回", "knowledge_recall"):
        recall_map = (
            _unified_recall(
                recall_terms,
                scope_code=ontology_code,
                field_layers=use_field_layers,
                value_layers=use_value_layers,
            )
            if recall_terms
            else {}
        )
        emit.result(
            {
                "terms": len(recall_terms),
                "recalled": sum(1 for v in recall_map.values() if v),
            }
        )

    # ── 召回为空时跳过 LLM 确认，直接报友好错误 ──
    _check_recall_not_empty(recall_terms, recall_map)

    # ── Step 4a: 主结构 LLM 确认 ──
    pre_resolved_input = _build_pre_resolved_input(structured_input, pre, main_terms)
    with emit.step("主结构确认", "llm_confirm_main"):
        main_context, term_registry = format_main_confirm_context(
            pre_resolved_input,
            main_terms,
            recall_map,
            pre,
            mode=mode,
            language=language,
        )
        main_result = llm_confirm_main(context=main_context, language=language, on_event=on_event)
        emit.result({"has_result": main_result is not None})

    resolution_hints = _build_main_resolution_hints(main_result, term_registry)
    _merge_pre_resolve_hints(resolution_hints, pre, main_terms, force_confirm=True)
    _merge_pre_resolve_hints(resolution_hints, cc_pre, cc_terms, force_confirm=True)

    # ── Step 4b: 逐条 cc LLM 确认 ──
    cc_results: list[tuple[Any, dict[Any, Any]]] = []
    if complex_conditions and cc_terms:
        cc_by_idx: dict[int, list[ExtractedTerm]] = {}
        for t in cc_terms:
            cc_by_idx.setdefault(t.condition_index, []).append(t)

        with emit.step("条件确认", "llm_confirm_cc"):
            for idx, sentence in enumerate(complex_conditions):
                group = cc_by_idx.get(idx, [])
                if not group:
                    continue
                cc_context, cc_registry = format_cc_confirm_context(
                    group,
                    recall_map,
                    sentence,
                    idx,
                    language=language,
                )
                cc_result = llm_confirm_cc(context=cc_context, language=language, on_event=on_event)
                cc_result = _normalize_cc_result_with_hints(
                    cc_result,
                    cc_registry,
                    resolution_hints,
                    recall_map,
                )
                _merge_cc_resolution_hints(resolution_hints, cc_result, cc_registry)
                cc_results.append((cc_result, cc_registry))
            emit.result({"cc_count": len(cc_results)})

    # ── Step 5: 合并 ──
    with emit.step("结果合并", "merge_confirmed"):
        confirmed = merge_confirmed(
            pre,
            main_result,
            cc_results,
            term_registry,
            structured_input,
            main_terms,
            recall_map=recall_map,
        )
        emit.result({"needs_clarification": confirmed.needs_clarification})

    # ── Step 6: 构建 paradigmList ──
    with emit.step("结果生成", "build_paradigm_list"):
        paradigm_list, meta = build_paradigm_list(
            confirmed,
            all_terms,
            recall_map,
            language=language,
            complex_conditions=complex_conditions,
            original_structured=structured_input,
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


def _check_recall_not_empty(
    recall_terms: list[Any],
    recall_map: dict[str, list[dict[str, Any]]],
) -> None:
    """当所有未解析术语检索均为空时，跳过 LLM 确认并报友好错误。"""
    from .models import ClarificationNoCandidatesError

    empty_terms: list[str] = []
    for t in recall_terms:
        key = f"{t.ktype}:{t.raw_text}"
        if not t.search_enabled:
            continue
        if not recall_map.get(key):
            empty_terms.append(t.raw_text)

    if empty_terms and all(
        not recall_map.get(f"{t.ktype}:{t.raw_text}") for t in recall_terms if t.search_enabled
    ):
        raise ClarificationNoCandidatesError(empty_terms)


# ── 格式化入口 ───────────────────────────────────────────────────────


def format_clarification_query(
    query: str,
    structured_query: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredQuery。"""
    return _format_query(query, structured_query, form, knowledge)


def format_clarification_compute(
    query: str,
    structured_compute: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredCompute。"""
    return _format_compute(query, structured_compute, form, knowledge)
