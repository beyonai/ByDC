"""LLM 确认 — 基于召回结果，一次调用确认主结构 + complex_conditions 术语。

输入：ExtractedTerm 列表 + 召回候选
输出：ConfirmedStructuredQuery / ConfirmedStructuredCompute
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from datacloud_knowledge.i18n import get_confirm_labels, get_confirm_prompt

from ._pre_resolve import extract_filter_prefix, term_key
from .models import (
    CCConfirmResult,
    CCTermMeta,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)

logger = logging.getLogger(__name__)

_CONFIRM_MAX_RETRIES = 2
_CONFIRM_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_CONFIRM_NON_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({400, 401, 403})


# ── 召回上下文格式化 ─────────────────────────────────────────────────


def format_recall_context(
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    *,
    language: str = "zh_CN",
    complex_conditions: list[str] | None = None,
    dimension_value_hints: dict[str, list[Any]] | None = None,
) -> str:
    """将术语 + 召回候选格式化为 LLM 可读的上下文。

    Args:
        terms: 提取的术语列表。
        recall_map: key 为 "ktype:raw_text"，value 为候选 dict 列表。
        language: 语言标识（"zh_CN" / "en_US"）。
        dimension_value_hints: 维度值线索。

    Returns:
        格式化的召回上下文文本。
    """
    labels = get_confirm_labels(language)
    no_recall = labels["no_recall_result"]
    lines: list[str] = []
    current_section = ""

    # 按 source 分区
    main_terms = [t for t in terms if t.source == "main"]
    cc_terms = [t for t in terms if t.source == "complex_condition"]

    # 主结构术语
    ktype_section_map = labels["ktype_section_query"]
    for term in main_terms:
        if not term.search_enabled:
            continue
        section = ktype_section_map.get(term.ktype, term.ktype)
        if section != current_section:
            if lines:
                lines.append("")
            lines.append(f"== {section} ==")
            current_section = section

        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        if not candidates:
            lines.append(f"  {term.raw_text} ({term.ktype}): {no_recall}")
        else:
            names = [str(c.get("term_name", "")) for c in candidates[:5]]
            lines.append(f"  {term.raw_text} ({term.ktype}): {names}")

    # complex_conditions 术语
    if cc_terms:
        lines.append("")
        lines.append("== complex_conditions 术语 ==")
        # 按 condition_index 分组
        by_idx: dict[int, list[ExtractedTerm]] = {}
        for t in cc_terms:
            by_idx.setdefault(t.condition_index, []).append(t)
        for idx in sorted(by_idx):
            group = by_idx[idx]
            # 输出原始句子
            original = ""
            if complex_conditions and idx < len(complex_conditions):
                original = complex_conditions[idx]
            lines.append(f'  [{idx}] "{original}":')

            # 合并别名扩展词的候选到父术语
            merged = _merge_alias_candidates(group, recall_map)
            for raw_text, ktype, names in merged:
                if not names:
                    lines.append(f"    {raw_text} ({ktype}): {no_recall}")
                else:
                    lines.append(f"    {raw_text} ({ktype}): {names}")

    # 维度值线索
    if dimension_value_hints:
        hint_lines: list[str] = []
        for keyword, hints in dimension_value_hints.items():
            for h in hints:
                span = getattr(h, "matched_span", "")
                value = getattr(h, "matched_value", "")
                dim = getattr(h, "dimension_prop", "")
                hint_lines.append(f'  {keyword}: "{span}" → {value} (维度={dim})')
        if hint_lines:
            lines.append("")
            lines.append("== 维度值线索（从短语中识别，辅助理解） ==")
            lines.extend(hint_lines)

    return "\n".join(lines)


# ── LLM 输出清洗 ──────────────────────────────────────────────────────

# LLM 可能在列表字段中传 null（如 select: [null]），或以 JSON 字符串传递列表
_LIST_FIELDS_TO_SANITIZE = (
    "select",
    "filters",
    "order_by",
    "dimensions",
    "metrics",
    "having",
    "clarify_items",
    "confirmed_conditions",
)


def _sanitize_confirm_args(args: dict[str, Any]) -> None:
    """清洗 LLM tool call 参数：JSON 字符串解码 + 过滤列表中的 None 值。"""
    for field in _LIST_FIELDS_TO_SANITIZE:
        val = args.get(field)
        # LLM 有时以 JSON 字符串传递列表/对象
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    val = parsed
                    args[field] = val
            except (json.JSONDecodeError, ValueError):
                pass
        if isinstance(val, list):
            args[field] = [item for item in val if item is not None]


# ── LLM 调用 ─────────────────────────────────────────────────────────


def llm_confirm_structured(
    *,
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: Literal["query", "compute"],
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> ConfirmedStructuredQuery | ConfirmedStructuredCompute | None:
    """调用 LLM 确认结构化查询中的术语。

    Args:
        query: 用户原始查询。
        structured_input: StructuredQuery 或 StructuredCompute 的 dict。
        recall_context: 格式化的召回上下文。
        mode: "query" 或 "compute"。
        on_event: 可选回调。

    Returns:
        确认后的结构，LLM 失败时返回 None。
    """
    if not recall_context.strip():
        logger.info("[confirm] 召回结果为空，跳过 LLM 确认")
        return None

    _collecting = os.environ.get("DATACLOUD_COLLECT_CONFIRM_CASES") == "1"
    _collect_input: dict[str, Any] | None = None
    if _collecting:
        _collect_input = {
            "query": query,
            "structured_input": structured_input,
            "recall_context": recall_context,
            "mode": mode,
        }

    model_cls: type[ConfirmedStructuredQuery] | type[ConfirmedStructuredCompute] = (
        ConfirmedStructuredQuery if mode == "query" else ConfirmedStructuredCompute
    )

    user_prompt = _build_user_prompt(
        query, structured_input, recall_context, mode, language=language
    )
    logger.debug("[confirm] recall_context:\n%s", recall_context)

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([model_cls])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": get_confirm_prompt(language, "main_legacy")},
                    {"role": "user", "content": user_prompt},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            # LLM 可能在列表字段中传 null（如 select: [null]），清洗后再校验
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False),
            )
            result = model_cls.model_validate(args)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result

        # 兜底：从 content 文本中提取 JSON
        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm] LLM 未返回 tool call，尝试从文本提取 JSON")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = model_cls.model_validate(fallback)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result
        logger.warning("[confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm] LLM 确认失败")
    if _collect_input is not None:
        _save_test_case(_collect_input, None)
    return None


def _is_retryable_confirm_error(exc: Exception) -> bool:
    """Return whether a clarification confirm failure is likely transient."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None:
        if int(status) in _CONFIRM_NON_RETRYABLE_HTTP_STATUS:
            return False
        return int(status) in _CONFIRM_RETRYABLE_HTTP_STATUS
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return isinstance(exc, ValueError) and "No generations found in stream" in str(exc)


def _invoke_confirm_with_retry(invoke: Callable[[], Any]) -> Any:
    """Invoke confirmation LLM call with minimal retry for transient failures."""
    last_exc: Exception | None = None

    for attempt in range(_CONFIRM_MAX_RETRIES + 1):
        try:
            return invoke()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_confirm_error(exc) or attempt >= _CONFIRM_MAX_RETRIES:
                raise

            wait_seconds = float(2**attempt)
            logger.warning(
                "[confirm] LLM 确认调用失败，第 %d/%d 次重试，等待 %.1f 秒: %s",
                attempt + 1,
                _CONFIRM_MAX_RETRIES,
                wait_seconds,
                exc,
            )
            time.sleep(wait_seconds)

    if last_exc is None:
        raise RuntimeError("confirm retry loop exited without result")
    raise last_exc


# ── 数据采集（DATACLOUD_COLLECT_CONFIRM_CASES=1 时启用）───────────────

_TEST_CASE_FILE = (
    Path(__file__).resolve().parents[4] / "scripts" / "manual" / "llm_confirm_test_cases.json"
)


def _save_test_case(
    case_input: dict[str, Any],
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute | None,
) -> None:
    """追加一条测试用例到 JSON 文件。采集失败不影响主流程。"""
    try:
        cases: list[dict[str, Any]] = []
        if _TEST_CASE_FILE.exists():
            cases = json.loads(_TEST_CASE_FILE.read_text("utf-8"))

        cases.append(
            {
                **case_input,
                "result": result.model_dump() if result is not None else None,
            }
        )

        _TEST_CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_CASE_FILE.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("[confirm] 测试用例已保存: %s (共 %d 条)", _TEST_CASE_FILE.name, len(cases))
    except Exception:
        logger.debug("[confirm] 测试用例保存失败，忽略", exc_info=True)


def _merge_alias_candidates(
    group: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str, list[str]]]:
    """将别名扩展词的召回候选合并到父术语，去重后统一展示。

    别名（parent_raw_text 非 None）的候选合并到对应父术语行，
    别名自身不再单独展示。每个术语的候选在召回阶段已经 top_k 截断，
    合并后只做去重，不再二次截断，避免丢失别名带来的有价值候选。

    Args:
        group: 同一 condition_index 下的术语列表。
        recall_map: 召回结果映射。

    Returns:
        [(raw_text, ktype, candidate_names), ...] 仅包含原始词（非别名）。
    """
    # 收集每个原始词的候选（含别名贡献）
    # key = (ktype, raw_text)
    parent_order: list[tuple[str, str]] = []
    parent_seen: set[tuple[str, str]] = set()
    merged_names: dict[tuple[str, str], list[str]] = {}

    for term in group:
        if not term.search_enabled:
            continue
        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        names = [str(c.get("term_name", "")) for c in candidates]

        if term.parent_raw_text is not None:
            # 别名 → 合并到父术语
            parent_key = (term.ktype, term.parent_raw_text)
            if parent_key not in parent_seen:
                parent_seen.add(parent_key)
                parent_order.append(parent_key)
                merged_names[parent_key] = []
            merged_names[parent_key].extend(names)
        else:
            # 原始词
            self_key = (term.ktype, term.raw_text)
            if self_key not in parent_seen:
                parent_seen.add(self_key)
                parent_order.append(self_key)
                merged_names[self_key] = []
            merged_names[self_key].extend(names)

    # 去重 + 截取 top 5
    result: list[tuple[str, str, list[str]]] = []
    for ktype, raw_text in parent_order:
        all_names = merged_names[(ktype, raw_text)]
        seen: set[str] = set()
        deduped: list[str] = []
        for name in all_names:
            if name and name not in seen:
                seen.add(name)
                deduped.append(name)
        result.append((raw_text, ktype, deduped))
    return result


def _build_user_prompt(
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: str,
    *,
    language: str = "zh_CN",
) -> str:
    labels = get_confirm_labels(language)
    mode_label = "StructuredQuery" if mode == "query" else "StructuredCompute"
    return f"""\
{labels["user_query"]}
{query}

{labels["user_structured_input"].format(mode=mode_label)}
{json.dumps(structured_input, ensure_ascii=False, indent=2)}

{labels["user_recall"]}
{recall_context}

{labels["user_submit"]}
{labels["user_instruction"]}"""


def _check_needs_clarification(
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
) -> bool:
    """判断是否需要用户澄清。"""
    if result.clarify_items:
        return True
    for cc in result.confirmed_conditions:
        for tm in cc.term_mappings:
            if tm.confirmed is None and tm.candidates:
                return True
    return False


# ── 分治确认上下文格式化 ─────────────────────────────────────────────


def format_main_confirm_context(
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    pre_resolve: PreResolveResult,
    *,
    mode: str = "query",
    language: str = "zh_CN",
) -> tuple[str, dict[int, TermMeta]]:
    """格式化主结构 LLM 确认上下文（编号术语模式）。

    Args:
        structured_input: 已做 pre_resolve 替换后的结构化输入。
        main_terms: 主结构提取的术语列表。
        recall_map: 召回结果映射。
        pre_resolve: pre_resolve 阶段输出。
        mode: "query" 或 "compute"。
        language: 语言标识（"zh_CN" / "en_US"）。

    Returns:
        (formatted_context, term_registry) 元组。
    """
    labels = get_confirm_labels(language)
    mode_label = "StructuredQuery" if mode == "query" else "StructuredCompute"
    lines: list[str] = []

    # 结构化输入（上下文参考）
    lines.append(labels["section_structured_input"].format(mode=mode_label))
    lines.append(json.dumps(structured_input, ensure_ascii=False, indent=2))
    lines.append("")

    # 已确认字段（按 path 键入，显示时用 raw_text）
    if pre_resolve.confirmed:
        lines.append(labels["section_confirmed"])
        # 收集已确认术语的 raw_text → term_name 映射（用于显示）
        shown: set[str] = set()
        for t in main_terms:
            if t.source != "main" or term_key(t) not in pre_resolve.confirmed:
                continue
            rf = pre_resolve.confirmed[term_key(t)]
            display_key = f"{rf.term_name}←{t.raw_text}"
            if display_key in shown:
                continue
            shown.add(display_key)
            source_tag = pre_resolve.provenance.get(term_key(t), "")
            tag_label = labels.get(f"source_tag_{source_tag}", source_tag)
            lines.append(f"  {rf.term_name} ← {t.raw_text}（{tag_label}）")
        lines.append("")

    # 编号待确认术语
    term_registry: dict[int, TermMeta] = {}
    term_id = 0

    # 按 ktype 分组展示
    ktype_section_map = labels["ktype_section_main"]

    unresolved_terms = [
        t
        for t in main_terms
        if t.source == "main"
        and t.search_enabled
        and term_key(t) not in pre_resolve.confirmed
        and t.parent_raw_text is None  # 跳过别名扩展词
    ]

    if unresolved_terms:
        lines.append(labels["section_pending"])
        current_section = ""
        for term in unresolved_terms:
            section = ktype_section_map.get(term.ktype, term.ktype)
            if section != current_section:
                current_section = section

            term_id += 1
            meta = TermMeta(path=term.path, ktype=term.ktype, raw_text=term.raw_text)
            term_registry[term_id] = meta

            key = f"{term.ktype}:{term.raw_text}"
            candidates = recall_map.get(key, [])
            names = [str(c.get("term_name", "")) for c in candidates]

            # whereValue 枚举约束（按 path 查找）
            enum_values = pre_resolve.value_enum_map.get(term_key(term))
            if enum_values is not None and term.ktype == "whereValue":
                where_key_name = _find_where_key_for_value(term, main_terms, pre_resolve)
                lines.append(
                    f"  #{term_id} {term.raw_text} ({section}，{labels['enum_values']}={where_key_name})"
                )
                lines.append(f"      {labels['enum_values']}: {enum_values}")
            else:
                lines.append(f"  #{term_id} {term.raw_text} ({section})")
                lines.append(f"      {labels['candidates']}: {names}")
            lines.append("")

    if not unresolved_terms:
        lines.append(labels["section_no_pending"])

    lines.append(labels["section_submit"])

    return "\n".join(lines), term_registry


def _find_term_position(
    sentence: str,
    term: str,
    used_positions: set[int],
) -> tuple[int, int]:
    """在句子中查找术语位置，避免与已占用位置冲突。"""
    term_len = len(term)
    occurrences: list[int] = []
    search_start = 0
    while True:
        idx = sentence.find(term, search_start)
        if idx == -1:
            break
        occurrences.append(idx)
        search_start = idx + 1

    if not occurrences:
        return -1, -1
    if len(occurrences) == 1:
        return occurrences[0], occurrences[0] + term_len
    # 多次出现 → 选未占用的第一个
    for occ in occurrences:
        if occ not in used_positions:
            return occ, occ + term_len
    return occurrences[0], occurrences[0] + term_len


def _find_where_key_for_value(
    value_term: ExtractedTerm,
    all_terms: list[ExtractedTerm],
    pre_resolve: PreResolveResult,
) -> str:
    """查找 whereValue 对应的 whereKey 中文名。"""
    # 从 path 推断：filters.N.value.M → filters.N 是 filter 前缀
    filter_prefix = extract_filter_prefix(value_term.path)
    if not filter_prefix:
        return "未知"
    for t in all_terms:
        if t.ktype == "whereKey" and extract_filter_prefix(t.path) == filter_prefix:
            rf = pre_resolve.confirmed.get(term_key(t))
            if rf:
                return rf.term_name
            return t.raw_text
    return "未知"


def format_cc_confirm_context(
    cc_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    sentence: str,
    condition_index: int,
    *,
    language: str = "zh_CN",
) -> tuple[str, dict[int, CCTermMeta]]:
    """格式化单条 complex_condition 的 LLM 确认上下文。

    Args:
        cc_terms: 该条 cc 的术语列表。
        recall_map: 召回结果映射。
        sentence: 原始条件句。
        condition_index: cc 索引。
        language: 语言标识（"zh_CN" / "en_US"）。

    Returns:
        (formatted_context, cc_term_registry) 元组。
    """
    labels = get_confirm_labels(language)
    lines: list[str] = []
    cc_term_registry: dict[int, CCTermMeta] = {}

    lines.append(labels["section_condition"])
    lines.append(f'"{sentence}"')
    lines.append("")

    # 合并别名候选到父术语
    merged = _merge_alias_candidates(cc_terms, recall_map)

    # 建立 raw_text → ExtractedTerm 映射（取第一个非别名的）
    raw_to_term: dict[str, ExtractedTerm] = {}
    for t in cc_terms:
        if t.parent_raw_text is None and t.raw_text not in raw_to_term:
            raw_to_term[t.raw_text] = t

    # 计算每个术语在句子中的位置（不依赖 LLM）
    used_positions: set[int] = set()
    ktype_label_map = labels["ktype_label_cc"]

    term_id = 0
    if merged:
        lines.append(labels["section_pending"])
        for raw_text, ktype, names in merged:
            term_id += 1

            # 从句子中查找位置
            start, end = _find_term_position(sentence, raw_text, used_positions)
            if start >= 0:
                used_positions.add(start)
            else:
                logger.warning(
                    "[confirm_cc] term '%s' not found in sentence, position set to 0/0",
                    raw_text,
                )

            meta = CCTermMeta(
                raw_text=raw_text,
                ktype=ktype,
                start=start if start >= 0 else 0,
                end=end if start >= 0 else 0,
                condition_index=condition_index,
            )
            cc_term_registry[term_id] = meta

            ktype_label = ktype_label_map.get(ktype, ktype)

            lines.append(f"  #{term_id} {raw_text} ({ktype_label})")
            if names:
                lines.append(f"      {labels['candidates']}: {names}")
            else:
                lines.append(f"      {labels['candidates']}: {labels['no_recall_result']}")
            lines.append("")

    lines.append(labels["section_submit"])

    return "\n".join(lines), cc_term_registry


# ── 分治 LLM 调用 ────────────────────────────────────────────────────


def llm_confirm_main(
    *,
    context: str,
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> MainConfirmResult | None:
    """调用 LLM 确认主结构术语（编号模式）。

    Args:
        context: format_main_confirm_context 生成的上下文。
        language: 语言标识（"zh_CN" / "en_US"）。
        on_event: 可选回调。

    Returns:
        MainConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_main] context empty, skip")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([MainConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": get_confirm_prompt(language, "main")},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_main] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = MainConfirmResult.model_validate(args)
            # 代码侧校正 needs_clarification
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result

        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm_main] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = MainConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_main] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_main] LLM 确认失败")
    return None


def llm_confirm_cc(
    *,
    context: str,
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> CCConfirmResult | None:
    """调用 LLM 确认单条 complex_condition 术语（编号模式）。

    Args:
        context: format_cc_confirm_context 生成的上下文。
        language: 语言标识（"zh_CN" / "en_US"）。
        on_event: 可选回调。

    Returns:
        CCConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_cc] context empty, skip")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([CCConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": get_confirm_prompt(language, "cc")},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_cc] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = CCConfirmResult.model_validate(args)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result

        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm_cc] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = CCConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_cc] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_cc] LLM 确认失败")
    return None
