"""LLM 确认 — 基于召回结果，生成真实 schema 的查询 or 触发澄清。

流程：
    NatQuery(NL 关键词) + 召回 candidates
        ↓
    LLM 审查每个关键词的召回结果：
      - 召回到复合度量 → 直接用 (select)
      - 召回到原子度量+维度 → 重构为维度过滤 (decompose)
      - 多个候选无法区分 → 标记需要用户澄清 (clarify)
        ↓
    输出：基于真实 schema 的 ConfirmedQuery + 是否需要澄清
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────


class ClarifyItem(BaseModel):
    """需要用户澄清的项。"""

    keyword: str = Field(description="原始自然语言关键词")
    candidates: list[str] = Field(description="候选术语列表，供用户选择")
    reason: str = Field(default="", description="需要澄清的原因")


class ConfirmedSelectExpr(BaseModel):
    """确认后的 SELECT 表达式，使用真实 schema 术语。"""

    expr: str = Field(description="真实术语名或派生表达式")
    alias: str = Field(default="", description="别名")
    original_keyword: str = Field(default="", description="展开前的原始 NL 关键词")


class ConfirmedWhereClause(BaseModel):
    """确认后的 WHERE 条件。"""

    field: str = Field(description="真实维度术语名")
    op: str = Field(default="=", description="运算符")
    value: Any = Field(description="过滤值")


class ConfirmedQuery(BaseModel):
    """LLM 确认后的查询：基于真实 schema 术语，标注需澄清项。

    LLM 根据召回结果：
    - 召回到完整复合度量 → 直接用作 SELECT expr
    - 召回到原子度量 + 维度字段 → 重构为 SELECT 原子度量 + WHERE 维度过滤
    - 多个候选无法区分 → 放入 clarify_items
    """

    select: list[ConfirmedSelectExpr] = Field(description="使用真实术语名的 SELECT 列表")
    where: list[ConfirmedWhereClause] = Field(
        default_factory=list,
        description="WHERE 条件（含重构后新增的维度过滤）",
    )
    group_by: list[str] = Field(
        default_factory=list,
        description="GROUP BY 维度（含重构后新增的）",
    )
    order_by: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None)
    clarify_items: list[ClarifyItem] = Field(
        default_factory=list,
        description="需要用户澄清的项：多个候选无法区分，或召回为空",
    )
    needs_clarification: bool = Field(
        default=False,
        description="是否需要用户澄清。clarify_items 非空时为 True",
    )


# ── Prompt ────────────────────────────────────────────────────────────

CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。根据知识库召回结果，将自然语言查询转为基于真实 schema 的结构化查询。

## 输入说明
- 用户原始查询和展开后的查询
- 每个关键词的知识库召回候选（候选名即真实字段名）
- 维度值线索：系统从短语中自动识别出的可能的维度过滤值（附所属维度和全部枚举值）

## 处理步骤

1. **确定 SELECT 字段**：从候选中选择最匹配的字段名。如果关键词含有聚合语义（如"均值""总数"），用 AVG/SUM/COUNT 包裹字段。
2. **识别隐含过滤条件**：结合维度值线索，如果关键词包含某个维度值的语义（线索区域会明确指出），则新增 WHERE 条件。使用线索中给出的**真实维度值**（而非用户原文）。
3. **确认 WHERE 字段**：用候选中的真实字段名替换用户原文中的自然语言字段名。
4. **判断是否需要澄清**：多个候选无法区分、或召回为空时，放入 clarify_items。

## 关键规则
- 所有字段名和维度值**只能**来自召回候选或维度值线索，严禁编造不存在的名称
- needs_clarification = true 当且仅当 clarify_items 非空
- 候选列表中排在前面的通常更相关，但要结合语义判断
- 维度值线索是辅助参考，非已确认条件；高置信线索可直接采用，低置信的应放入 clarify_items
"""


# ── 构建确认 prompt ──────────────────────────────────────────────────


def _format_recall_context(
    items: list[Any],
    dimension_value_hints: dict[str, list[Any]] | None = None,
) -> str:
    """将 TypedKeywordState 列表格式化为 LLM 可读的召回上下文。

    分两个区域：
    1. 字段候选（recall candidates）— 纯字段名，按相关度排序
    2. 维度值线索（dimension_value_hints）— 附维度名和全部枚举值
    """
    lines: list[str] = []
    current_paradigm = ""

    for item in items:
        paradigm = getattr(item, "paradigm_name", "")
        if paradigm != current_paradigm:
            if lines:
                lines.append("")
            lines.append(f"== {paradigm} ==")
            current_paradigm = paradigm

        keyword = getattr(item, "keyword", "")
        ktype = getattr(item, "ktype", "")
        candidates = getattr(item, "candidates", [])
        search_enabled = getattr(item, "search_enabled", True)

        if not search_enabled:
            lines.append(f"  {keyword} ({ktype}): 不参与召回")
            continue

        if not candidates:
            lines.append(f"  {keyword} ({ktype}): 无召回结果")
        else:
            names = [getattr(c, "term_name", str(c)) for c in candidates[:5]]
            lines.append(f"  {keyword} ({ktype}): {names}")

    # 维度值线索区域：按维度去重汇总
    if dimension_value_hints:
        # 收集每个 keyword 的线索，同维度只显示一次枚举表
        hint_lines: list[str] = []
        shown_dims: set[str] = set()
        resolver = _get_resolver()
        for keyword, hints in dimension_value_hints.items():
            for h in hints:
                span = getattr(h, "matched_span", "")
                value = getattr(h, "matched_value", "")
                dim = getattr(h, "dimension_prop", "")
                enum_part = ""
                if dim not in shown_dims and resolver:
                    enum_values = resolver.get_dim_enum(dim)
                    if enum_values:
                        enum_part = f"（{dim}全部值: {enum_values}）"
                        shown_dims.add(dim)
                hint_lines.append(f'  {keyword}: "{span}" → {value} (维度={dim}){enum_part}')
        if hint_lines:
            lines.append("")
            lines.append("== 维度值线索（从短语中识别，辅助理解） ==")
            lines.extend(hint_lines)

    return "\n".join(lines)


def _get_resolver() -> Any:
    """懒获取 DimensionValueResolver，不可用时返回 None。"""
    try:
        from .dimension_values import DimensionValueResolver  # noqa: PLC0415

        return DimensionValueResolver.get_instance()
    except Exception:
        return None


def _build_confirm_user_prompt(
    original_question: str,
    expanded_query: str,
    recall_context: str,
) -> str:
    return f"""\
## 用户原始查询
{original_question}

## 展开后的查询
{expanded_query}

## 知识库召回结果
{recall_context}

## 请输出确认后的查询
根据召回结果，生成基于真实 schema 术语的结构化查询。"""


# ── 公共 API ─────────────────────────────────────────────────────────


def llm_confirm(
    original_question: str,
    expanded_query: str,
    state: Any,
    on_event: Callable[[Any], None] | None = None,
) -> ConfirmedQuery | None:
    """基于召回结果，调 LLM 生成真实 schema 的确认查询。

    Args:
        original_question: 用户原始查询。
        expanded_query: NatQuery 展开后的查询文本。
        state: ParadigmResolutionState（含 items + candidates）。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        ConfirmedQuery 实例，LLM 失败时返回 None。
    """
    items = getattr(state, "items", [])
    dim_hints = getattr(state, "dimension_value_hints", None)
    recall_context = _format_recall_context(items, dimension_value_hints=dim_hints)

    if not recall_context.strip():
        logger.info("[llm_confirm] 召回结果为空，跳过 LLM 确认")
        return None

    user_prompt = _build_confirm_user_prompt(
        original_question,
        expanded_query,
        recall_context,
    )
    logger.debug("[llm_confirm] 知识上下文:\n%s", recall_context)
    logger.debug("[llm_confirm] user_prompt:\n%s", user_prompt)

    try:
        from .llm_utils import build_llm, extract_json_from_text, stream_invoke_with_thinking  # noqa: PLC0415

        llm = build_llm()
        llm_with_tool = llm.bind_tools(
            [ConfirmedQuery],
            # tool_choice="ConfirmedQuery",
        )
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
                "[llm_confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False),
            )
            result = ConfirmedQuery.model_validate(args)
            result.needs_clarification = len(result.clarify_items) > 0
            return result

        # 兜底：从 content 文本中提取 JSON
        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[llm_confirm] LLM 未返回 tool call，尝试从文本提取 JSON")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            logger.info(
                "[llm_confirm] 兜底提取成功: %s",
                json.dumps(fallback, ensure_ascii=False),
            )
            result = ConfirmedQuery.model_validate(fallback)
            result.needs_clarification = len(result.clarify_items) > 0
            return result
        logger.warning("[llm_confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[llm_confirm] LLM 确认失败")
    return None
