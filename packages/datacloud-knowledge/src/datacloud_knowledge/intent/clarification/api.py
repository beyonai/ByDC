"""澄清模块编排层 — 澄清分析与格式化公共入口。

公共 API：
    - analyze_query_clarification
    - format_clarification_query
    - format_clarification_compute
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from collections.abc import Callable
from typing import Any, Literal, Protocol

from datacloud_knowledge.intent.llm_utils import EventEmitter
from datacloud_knowledge.intent.types import ClarificationResult

from .cartesian import build_paradigm_list, serialize_knowledge_meta, serialize_paradigm_payload
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
from .models import (
    CCConfirmResult,
    CCTermMeta,
    ClarifyItem,
    ConditionTermMapping,
    ConfirmedCondition,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)

logger = logging.getLogger(__name__)

ClarificationMode = Literal["query", "compute"]
ConfirmedStructured = ConfirmedStructuredQuery | ConfirmedStructuredCompute


class _MergeConfirmed(Protocol):
    """将公共确认结果合并为指定结构类型。"""

    def __call__(
        self,
        pre: PreResolveResult,
        main_result: MainConfirmResult | None,
        cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
        term_registry: dict[int, TermMeta],
        structured_input: dict[str, Any],
        main_terms: list[ExtractedTerm],
        *,
        recall_map: dict[str, list[dict[str, Any]]] | None = None,
    ) -> ConfirmedStructured: ...


# ── 分析入口 ─────────────────────────────────────────────────────────


def analyze_query_clarification(
    query: str,
    ontology_code: str,
    structured_input: dict[str, Any],
    *,
    mode: ClarificationMode,
    on_event: Callable[[Any], None] | None = None,
) -> ClarificationResult:
    """分析 StructuredQuery/StructuredCompute 是否需要用户澄清。"""
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

    # ── Step 2: Pre-Resolve（主结构字段预解析）──
    with emit.step("字段预解析", "pre_resolve"):
        pre = _pre_resolve_terms(main_terms, scope_code=ontology_code)
        pre_result = {
            "confirmed": len(pre.confirmed),
            "unresolved": len(pre.unresolved_terms),
        }
        if mode == "query":
            pre_result["value_constraints"] = len(pre.value_enum_map)
        emit.result(pre_result)

    # ── Step 3: 定向召回（只对 unresolved 术语 + cc 术语）──
    recall_terms = list(pre.unresolved_terms) + cc_terms
    with emit.step("知识召回", "knowledge_recall"):
        recall_map = _unified_recall(recall_terms, scope_code=ontology_code) if recall_terms else {}
        emit.result(
            {"terms": len(recall_terms), "recalled": sum(1 for v in recall_map.values() if v)}
        )

    # ── Step 4a: 主结构 LLM 确认（编号术语模式）──
    pre_resolved_input = _build_pre_resolved_input(structured_input, pre, main_terms)
    with emit.step("主结构确认", "llm_confirm_main"):
        main_context, term_registry = format_main_confirm_context(
            pre_resolved_input,
            main_terms,
            recall_map,
            pre,
            mode=mode,
        )
        main_result = llm_confirm_main(context=main_context, on_event=on_event)
        emit.result({"has_result": main_result is not None})

    # ── Step 4b: 逐条 cc LLM 确认 ──
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]] = []
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
                )
                cc_result = llm_confirm_cc(context=cc_context, on_event=on_event)
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
    *,
    scope_code: str | None = None,
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
        result.update(typed_multi_recall_with_session(normal_items, top_k=5, scope_code=scope_code))

    # 英文标识符：只走向量召回（BM25/子串匹配对英文→中文无意义）
    if vector_only_items:
        result.update(_vector_only_recall(vector_only_items, top_k=5, scope_code=scope_code))

    return result


def _vector_only_recall(
    items: list[_RecallItem],
    *,
    top_k: int,
    scope_code: str | None = None,
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
                    scope_code=scope_code,
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


# ── 分治确认内部辅助 ─────────────────────────────────────────────────

_FIELD_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_field_code(term: str) -> bool:
    """判断术语是否为英文字段编码。"""
    return bool(_FIELD_CODE_RE.match(term))


def _term_key(t: ExtractedTerm) -> str:
    """生成术语的复合键：path:raw_text。"""
    return f"{t.path}:{t.raw_text}"


def _pre_resolve_terms(
    main_terms: list[ExtractedTerm],
    scope_code: str,
) -> PreResolveResult:
    """Phase 2: 预解析主结构术语。

    - 英文 field_code / 中文唯一精确命中 → confirmed_exact
    - 歧义 / 未命中 → unresolved，走 recall
    - 已确认 whereKey → 查 prop 枚举值约束 whereValue

    Args:
        main_terms: 主结构提取的术语列表。
        scope_code: 本体编码。

    Returns:
        PreResolveResult。
    """
    from datacloud_knowledge.knowledge_search.term_search import (
        get_prop_enum_values,
        resolve_field_aliases_with_names,
    )
    from datacloud_knowledge.knowledge_search.types import ResolvedField

    confirmed: dict[str, ResolvedField] = {}  # keyed by path
    provenance: dict[str, str] = {}  # keyed by path
    value_enum_map: dict[str, list[str]] = {}  # keyed by path

    # 收集字段类术语（非 whereValue），去重 raw_text 用于 SQL 查询
    field_terms_raw: list[str] = []
    for t in main_terms:
        if t.source != "main" or not t.search_enabled:
            continue
        if t.ktype == "whereValue" or t.parent_raw_text is not None:
            continue
        if t.raw_text not in field_terms_raw:
            field_terms_raw.append(t.raw_text)

    # 调用扩展版别名解析（返回 {raw_text → ResolvedField}）
    resolved_by_text: dict[str, ResolvedField] = {}
    if field_terms_raw and scope_code:
        try:
            result = resolve_field_aliases_with_names(
                terms=field_terms_raw,
                scope_code=scope_code,
            )
            resolved_by_text = result.resolved
            # 扇出到所有匹配的术语，按 path:raw_text 复合键入
            for t in main_terms:
                if t.source != "main" or t.ktype == "whereValue" or t.parent_raw_text is not None:
                    continue
                rf = resolved_by_text.get(t.raw_text)
                if rf:
                    tk = _term_key(t)
                    confirmed[tk] = rf
                    tag = "field_code" if _is_field_code(t.raw_text) else "alias_exact"
                    provenance[tk] = tag
            logger.info(
                "[pre_resolve] resolved=%d ambiguous=%d unresolved=%d",
                len(result.resolved),
                len(result.ambiguous),
                len(result.unresolved),
            )
        except Exception:
            logger.warning("[pre_resolve] resolve_field_aliases_with_names 失败", exc_info=True)

    # 已确认 whereKey → 查枚举值
    confirmed_key_codes: list[str] = []
    key_code_to_name: dict[str, str] = {}
    for t in main_terms:
        if t.ktype == "whereKey" and _term_key(t) in confirmed:
            rf = confirmed[_term_key(t)]
            if rf.term_code not in key_code_to_name:
                confirmed_key_codes.append(rf.term_code)
                key_code_to_name[rf.term_code] = rf.term_name

    if confirmed_key_codes and scope_code:
        try:
            enum_map = get_prop_enum_values(
                scope_code=scope_code,
                field_codes=confirmed_key_codes,
            )
            # 为每个 whereValue 术语建立枚举约束（按 path 键入）
            for t in main_terms:
                if t.ktype != "whereValue" or not t.search_enabled:
                    continue
                key_term = _find_paired_where_key(t, main_terms)
                if key_term and _term_key(key_term) in confirmed:
                    rf = confirmed[_term_key(key_term)]
                    enum_values = enum_map.get(rf.term_code, [])
                    if enum_values:
                        tk = _term_key(t)
                        value_enum_map[tk] = enum_values
                        # 尝试在枚举集内精确匹配
                        for ev in enum_values:
                            if ev == t.raw_text:
                                confirmed[tk] = ResolvedField(
                                    term_code=ev,
                                    term_name=ev,
                                )
                                provenance[tk] = "enum_exact"
                                break
        except Exception:
            logger.warning("[pre_resolve] get_prop_enum_values 失败", exc_info=True)

    # 分拣 unresolved
    unresolved: list[ExtractedTerm] = []
    for t in main_terms:
        if t.source != "main":
            continue
        if _term_key(t) in confirmed:
            continue
        unresolved.append(t)

    logger.info(
        "[pre_resolve] confirmed=%d unresolved=%d value_constraints=%d",
        len(confirmed),
        len(unresolved),
        len(value_enum_map),
    )

    return PreResolveResult(
        confirmed=confirmed,
        unresolved_terms=unresolved,
        value_enum_map=value_enum_map,
        provenance=provenance,
    )


def _find_paired_where_key(
    value_term: ExtractedTerm,
    all_terms: list[ExtractedTerm],
) -> ExtractedTerm | None:
    """查找 whereValue 对应的 whereKey 术语。"""
    filter_prefix = _extract_filter_prefix(value_term.path)
    if not filter_prefix:
        return None
    for t in all_terms:
        if t.ktype == "whereKey" and _extract_filter_prefix(t.path) == filter_prefix:
            return t
    return None


def _extract_filter_prefix(path: str) -> str:
    """从 path 提取 filter 前缀：'filters.1.field' → 'filters.1'。"""
    parts = path.split(".")
    if len(parts) >= 2 and parts[0] == "filters":
        return f"{parts[0]}.{parts[1]}"
    for i, p in enumerate(parts):
        if p == "filters" and i + 1 < len(parts):
            try:
                int(parts[i + 1])
                return ".".join(parts[: i + 2])
            except ValueError:
                pass
    return ""


def _build_pre_resolved_input(
    structured_input: dict[str, Any],
    pre_resolve: PreResolveResult,
    main_terms: list[ExtractedTerm],
) -> dict[str, Any]:
    """将已确认字段替换到 structured_input 中（用中文 term_name）。"""
    result = json.loads(json.dumps(structured_input, ensure_ascii=False))

    # 非 whereValue 字段直接替换
    for t in main_terms:
        if t.source != "main" or _term_key(t) not in pre_resolve.confirmed:
            continue
        if t.ktype == "whereValue":
            continue
        rf = pre_resolve.confirmed[_term_key(t)]
        _set_by_path(result, t.path, rf.term_name)

    # whereValue 列表感知替换
    _apply_confirmed_values(result, main_terms, pre_resolve.confirmed)

    # 移除 complex_conditions（主结构不需要）
    result.pop("complex_conditions", None)
    return result


def _set_by_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """按 JSON pointer 路径设置值。"""
    parts = path.split(".")
    current: Any = obj
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return
        else:
            return
    if current is None:
        return
    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        with contextlib.suppress(ValueError, IndexError):
            current[int(last)] = value


def _apply_value_list(
    obj: dict[str, Any],
    value_path: str,
    idx_vals: list[tuple[int, str]],
) -> None:
    """按索引替换 filter value 列表中的元素（不覆盖整个列表）。

    Args:
        obj: 结构化输入。
        value_path: 如 'filters.0.value'。
        idx_vals: [(列表内索引, 确认值)] 列表。
    """
    parts = value_path.split(".")
    current: Any = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return
        else:
            return
        if current is None:
            return

    if isinstance(current, list):
        for idx, val in idx_vals:
            if 0 <= idx < len(current):
                current[idx] = val
    elif idx_vals:
        # 标量 value → 直接用最后一个确认值覆盖
        _set_by_path(obj, value_path, idx_vals[-1][1])


def _apply_confirmed_values(
    obj: dict[str, Any],
    main_terms: list[ExtractedTerm],
    confirmed: dict[str, Any],
    *,
    term_source: str = "",
) -> None:
    """批量回填已确认的 whereValue 到 filter value 列表。"""
    # 按 value path 分组
    by_path: dict[str, list[tuple[int, str]]] = {}
    path_counters: dict[str, int] = {}
    for t in main_terms:
        if t.source != "main" or t.ktype != "whereValue":
            continue
        tk = _term_key(t)
        if tk not in confirmed:
            continue
        rf = confirmed[tk]
        idx = path_counters.get(t.path, 0)
        path_counters[t.path] = idx + 1
        term_name = rf.term_name if hasattr(rf, "term_name") else str(rf)
        by_path.setdefault(t.path, []).append((idx, term_name))

    for vpath, idx_vals in by_path.items():
        _apply_value_list(obj, vpath, idx_vals)


def _recall_fallback_candidates(
    recall_map: dict[str, list[dict[str, Any]]] | None,
    ktype: str,
    raw_text: str,
    limit: int = 5,
) -> list[str]:
    """从召回结果中提取 term_name 列表作为兜底候选。"""
    if not recall_map:
        return []
    key = f"{ktype}:{raw_text}"
    candidates = recall_map.get(key, [])
    return [str(c.get("term_name", "")) for c in candidates[:limit] if c.get("term_name")]


def _merge_confirmed_common(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], list[ClarifyItem], list[ConfirmedCondition], bool]:
    """合并分治确认结果的共享逻辑。

    Returns:
        (patched_result, clarify_items, confirmed_conditions, needs_clarification)
    """
    result = json.loads(json.dumps(structured_input, ensure_ascii=False))

    # 1. 回填 pre_resolve 已确认字段（非 whereValue）
    for t in main_terms:
        if t.source != "main" or _term_key(t) not in pre.confirmed:
            continue
        if t.ktype == "whereValue":
            continue  # whereValue 列表需要特殊处理
        rf = pre.confirmed[_term_key(t)]
        _set_by_path(result, t.path, rf.term_name)

    # 1b. 回填 pre_resolve 已确认的 whereValue（列表感知）
    _apply_confirmed_values(result, main_terms, pre.confirmed, term_source="pre_resolve")

    # 2. 回填 main LLM 确认结果（fail-closed: LLM 失败时强制澄清）
    clarify_items: list[ClarifyItem] = []
    llm_failed = False
    # 收集 whereValue 的 LLM 确认结果，稍后批量回填
    value_confirmations: dict[
        str, list[tuple[int, str]]
    ] = {}  # path → [(index_in_list, confirmed)]
    if main_result:
        covered_ids: set[int] = set()
        # 先统计每个 value path 下有多少个术语（用于确定列表索引）
        value_path_counters: dict[str, int] = {}
        for tc in main_result.confirmations:
            meta = term_registry.get(tc.term_id)
            if meta is None:
                continue
            covered_ids.add(tc.term_id)
            if meta.ktype == "whereValue" and tc.confirmed:
                idx = value_path_counters.get(meta.path, 0)
                value_path_counters[meta.path] = idx + 1
                value_confirmations.setdefault(meta.path, []).append((idx, tc.confirmed))
            elif tc.confirmed:
                _set_by_path(result, meta.path, tc.confirmed)
            elif tc.candidates:
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=tc.candidates,
                        reason=tc.reason,
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )
            else:
                # confirmed=None, candidates=[] → fail-closed
                # 从召回结果回填 candidates，避免空候选列表
                llm_failed = True
                fallback_candidates = _recall_fallback_candidates(
                    recall_map, meta.ktype, meta.raw_text
                )
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=fallback_candidates,
                        reason=tc.reason or "LLM 无法确认且无候选",
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )
        # 检查 LLM 遗漏的 term_id → 强制澄清
        missing_ids = set(term_registry) - covered_ids
        if missing_ids:
            llm_failed = True
            logger.warning(
                "[merge] LLM 遗漏 %d 个术语: %s",
                len(missing_ids),
                [term_registry[tid].raw_text for tid in missing_ids],
            )
            for tid in missing_ids:
                meta = term_registry[tid]
                fallback_candidates = _recall_fallback_candidates(
                    recall_map, meta.ktype, meta.raw_text
                )
                clarify_items.append(
                    ClarifyItem(
                        keyword=meta.raw_text,
                        candidates=fallback_candidates,
                        reason="LLM 确认遗漏，需要人工确认",
                        source=meta.ktype,
                        path=f"/{meta.path.replace('.', '/')}",
                    )
                )

        # 批量回填 whereValue 列表（列表感知，不覆盖整个 value）
        for vpath, idx_vals in value_confirmations.items():
            _apply_value_list(result, vpath, idx_vals)

    elif term_registry:
        # LLM 失败但有未确认术语 → fail-closed，强制澄清
        llm_failed = True
        logger.warning("[merge] main LLM 确认失败，%d 个术语强制标记为需澄清", len(term_registry))
        for meta in term_registry.values():
            fallback_candidates = _recall_fallback_candidates(recall_map, meta.ktype, meta.raw_text)
            clarify_items.append(
                ClarifyItem(
                    keyword=meta.raw_text,
                    candidates=fallback_candidates,
                    reason="LLM 确认失败，需要人工确认",
                    source=meta.ktype,
                    path=f"/{meta.path.replace('.', '/')}",
                )
            )

    # 3. 组装 confirmed_conditions（fail-closed: cc LLM 失败时也强制澄清）
    confirmed_conditions: list[ConfirmedCondition] = []
    for cc_result, cc_registry in cc_results:
        if cc_result is None:
            if cc_registry:
                # CC LLM 失败但有术语 → 强制澄清
                llm_failed = True
                logger.warning(
                    "[merge] cc LLM 确认失败，%d 个术语强制标记为需澄清",
                    len(cc_registry),
                )
                for meta in cc_registry.values():
                    clarify_items.append(
                        ClarifyItem(
                            keyword=meta.raw_text,
                            candidates=[],
                            reason="LLM 确认失败，需要人工确认",
                            source="complex_condition",
                            path=f"complex_conditions.{meta.condition_index}",
                        )
                    )
            continue
        if not cc_registry:
            continue
        by_idx: dict[int, list[tuple[int, CCTermMeta]]] = {}
        for tid, meta in cc_registry.items():
            by_idx.setdefault(meta.condition_index, []).append((tid, meta))

        for idx in sorted(by_idx):
            items = by_idx[idx]
            cc_list = structured_input.get("complex_conditions", [])
            original = cc_list[idx] if idx < len(cc_list) else ""

            term_mappings: list[ConditionTermMapping] = []
            for tid, meta in items:
                tc = next((c for c in cc_result.confirmations if c.term_id == tid), None)
                if tc is None:
                    # LLM 遗漏该术语 → 强制标记为需澄清
                    llm_failed = True
                    logger.warning("[merge] cc LLM 遗漏术语 '%s'", meta.raw_text)
                    term_mappings.append(
                        ConditionTermMapping(
                            original_term=meta.raw_text,
                            start=meta.start,
                            end=meta.end,
                            confirmed=None,
                            candidates=[],
                        )
                    )
                    clarify_items.append(
                        ClarifyItem(
                            keyword=meta.raw_text,
                            candidates=[],
                            reason="LLM 确认遗漏，需要人工确认",
                            source="complex_condition",
                            path=f"complex_conditions.{meta.condition_index}",
                        )
                    )
                    continue
                term_mappings.append(
                    ConditionTermMapping(
                        original_term=meta.raw_text,
                        start=meta.start,
                        end=meta.end,
                        confirmed=tc.confirmed,
                        candidates=tc.candidates,
                    )
                )
                if tc.confirmed is None and tc.candidates:
                    clarify_items.append(
                        ClarifyItem(
                            keyword=meta.raw_text,
                            candidates=tc.candidates,
                            reason=tc.reason,
                            source="complex_condition",
                            path=f"complex_conditions.{idx}",
                        )
                    )
                elif tc.confirmed is None:
                    # confirmed=None, candidates=[] → fail-closed
                    llm_failed = True
                    clarify_items.append(
                        ClarifyItem(
                            keyword=meta.raw_text,
                            candidates=[],
                            reason=tc.reason or "LLM 无法确认且无候选",
                            source="complex_condition",
                            path=f"complex_conditions.{idx}",
                        )
                    )

            confirmed_conditions.append(
                ConfirmedCondition(
                    original_sentence=original,
                    term_mappings=term_mappings,
                )
            )

    needs = (
        llm_failed
        or bool(clarify_items)
        or any(
            tm.confirmed is None and tm.candidates
            for cc in confirmed_conditions
            for tm in cc.term_mappings
        )
    )

    return result, clarify_items, confirmed_conditions, needs


def _merge_to_confirmed_query(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> ConfirmedStructuredQuery:
    """合并分治确认结果为 ConfirmedStructuredQuery（兼容下游）。"""
    result, clarify_items, confirmed_conditions, needs = _merge_confirmed_common(
        pre,
        main_result,
        cc_results,
        term_registry,
        structured_input,
        main_terms,
        recall_map=recall_map,
    )
    return ConfirmedStructuredQuery(
        select=result.get("select", []),
        filters=result.get("filters", []),
        order_by=result.get("order_by", []),
        limit=result.get("limit"),
        offset=result.get("offset"),
        filter_relation=result.get("filter_relation", "AND"),
        confirmed_conditions=confirmed_conditions,
        clarify_items=clarify_items,
        needs_clarification=needs,
    )


def _merge_to_confirmed_compute(
    pre: PreResolveResult,
    main_result: MainConfirmResult | None,
    cc_results: list[tuple[CCConfirmResult | None, dict[int, CCTermMeta]]],
    term_registry: dict[int, TermMeta],
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]] | None = None,
) -> ConfirmedStructuredCompute:
    """合并分治确认结果为 ConfirmedStructuredCompute（兼容下游）。"""
    result, clarify_items, confirmed_conditions, needs = _merge_confirmed_common(
        pre,
        main_result,
        cc_results,
        term_registry,
        structured_input,
        main_terms,
        recall_map=recall_map,
    )
    return ConfirmedStructuredCompute(
        dimensions=result.get("dimensions", []),
        metrics=result.get("metrics", []),
        filters=result.get("filters", []),
        having=result.get("having", []),
        order_by=result.get("order_by", []),
        limit=result.get("limit"),
        filter_relation=result.get("filter_relation", "AND"),
        confirmed_conditions=confirmed_conditions,
        clarify_items=clarify_items,
        needs_clarification=needs,
    )
