"""LLM 确认 — 基于召回结果，一次调用确认主结构 + complex_conditions 术语。

输入：ExtractedTerm 列表 + 召回候选
输出：ConfirmedStructuredQuery / ConfirmedStructuredCompute
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, Literal

from .models import (
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
)

logger = logging.getLogger(__name__)


# ── System Prompt ────────────────────────────────────────────────────


CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。根据知识库召回结果，将结构化查询中的中文术语映射到真实 schema 字段。

## 输入
- 用户原始查询
- 结构化查询参数（StructuredQuery 或 StructuredCompute）
- 每个中文术语的知识库召回候选
- 维度值线索

## 主结构确认规则
- 所有字段名和维度值只能来自召回候选或维度值线索，严禁编造
- 确定的术语直接替换为真实字段名
- 无法确定的放入 clarify_items，标注 source 和 path
- 候选列表中排在前面的通常更相关，但要结合语义判断

## complex_conditions 确认规则
- 对每条 NL 中的中文术语做确认
- 输出 original_term / start / end / confirmed / candidates
- 只有一个高置信候选 → confirmed 填值
- 多候选无法区分 → confirmed = null，candidates 按相关度排序

## 关键规则
- needs_clarification = true ⟺ clarify_items 非空 或任何 complex_condition 术语的 confirmed 为 null
- clarify_items 中的 source 必须标明来源: "select" / "where" / "group_by" / "order_by"
- 严禁编造不存在的字段名
"""


# ── 召回上下文格式化 ─────────────────────────────────────────────────


def format_recall_context(
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    *,
    complex_conditions: list[str] | None = None,
    dimension_value_hints: dict[str, list[Any]] | None = None,
) -> str:
    """将术语 + 召回候选格式化为 LLM 可读的上下文。

    Args:
        terms: 提取的术语列表。
        recall_map: key 为 "ktype:raw_text"，value 为候选 dict 列表。
        dimension_value_hints: 维度值线索。

    Returns:
        格式化的召回上下文文本。
    """
    lines: list[str] = []
    current_section = ""

    # 按 source 分区
    main_terms = [t for t in terms if t.source == "main"]
    cc_terms = [t for t in terms if t.source == "complex_condition"]

    # 主结构术语
    ktype_section_map = {
        "select": "查询值",
        "groupBy": "分组条件",
        "whereKey": "过滤条件（字段）",
        "whereValue": "过滤条件（值）",
        "orderBy": "排序目标",
    }
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
            lines.append(f"  {term.raw_text} ({term.ktype}): 无召回结果")
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
            for term in group:
                if not term.search_enabled:
                    continue
                key = f"{term.ktype}:{term.raw_text}"
                candidates = recall_map.get(key, [])
                if not candidates:
                    lines.append(f"    {term.raw_text} ({term.ktype}): 无召回结果")
                else:
                    names = [str(c.get("term_name", "")) for c in candidates[:5]]
                    lines.append(f"    {term.raw_text} ({term.ktype}): {names}")

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


# ── LLM 调用 ─────────────────────────────────────────────────────────


def llm_confirm_structured(
    *,
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: Literal["query", "compute"],
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

    model_cls: type[ConfirmedStructuredQuery] | type[ConfirmedStructuredCompute] = (
        ConfirmedStructuredQuery if mode == "query" else ConfirmedStructuredCompute
    )

    user_prompt = _build_user_prompt(query, structured_input, recall_context, mode)
    logger.debug("[confirm] recall_context:\n%s", recall_context)

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([model_cls])
        response = stream_invoke_with_thinking(
            llm_with_tool,
            [
                {"role": "system", "content": CONFIRM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            on_event=on_event,
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            logger.info(
                "[confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = model_cls.model_validate(args)
            result.needs_clarification = _check_needs_clarification(result)
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
            return result
        logger.warning("[confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm] LLM 确认失败")
    return None


def _build_user_prompt(
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: str,
) -> str:
    mode_label = "StructuredQuery" if mode == "query" else "StructuredCompute"
    return f"""\
## 用户原始查询
{query}

## 结构化输入（{mode_label}）
{json.dumps(structured_input, ensure_ascii=False, indent=2)}

## 知识库召回结果
{recall_context}

## 请输出确认后的结构
根据召回结果，将中文术语映射到真实 schema 字段。"""


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
