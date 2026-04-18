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
    source: str = Field(
        default="",
        description="来源槽位: select / where / group_by / order_by",
    )


class DimensionFilter(BaseModel):
    """业务限定条件 — 语义化的维度过滤。

    用户看到的是 "成绩等级 = 优秀"，而非 CASE WHEN SQL。
    """

    dimension: str = Field(description="真实维度字段名，如 '成绩等级'")
    op: str = Field(default="=", description="运算符: =, IN, !=")
    value: str | list[str] = Field(description="维度值，如 '优秀' 或 ['及格', '良好']")


class ConfirmedSelectExpr(BaseModel):
    """语义化的 SELECT 表达式 — 用户可读，规则可还原 SQL。

    结构：业务限定(filters) + 度量(measure) + 分母(denominator) + 统计函数(agg_func)

    示例：
      - 直接字段: measure="班级综合平均分（分）"
      - 聚合度量: measure="学生人数", agg_func="COUNT"
      - 条件计数占比: measure="*", agg_func="RATIO",
                      filters=[DimensionFilter(dimension="成绩等级", value="优秀")]
      - 金额占比: measure="竞赛获奖人数", denominator="班级总人数",
                  agg_func="RATIO"
    """

    original_keyword: str = Field(default="", description="展开前的原始 NL 关键词")
    measure: str = Field(description="度量字段名（真实术语名）或 '*'")
    denominator: str = Field(
        default="",
        description="分母度量字段名，非空时表示比率计算: SUM(measure)/SUM(denominator)*100",
    )
    agg_func: str = Field(
        default="",
        description="聚合函数: SUM / COUNT / AVG / MIN / MAX / RATIO，空串表示直接取值",
    )
    filters: list[DimensionFilter] = Field(
        default_factory=list,
        description="业务限定条件列表，如 [成绩等级=优秀]",
    )
    alias: str = Field(default="", description="展示别名")


class ConfirmedWhereClause(BaseModel):
    """确认后的 WHERE 条件。"""

    field: str = Field(description="真实维度术语名")
    op: str = Field(default="=", description="运算符")
    value: Any = Field(description="过滤值")
    original_field_keyword: str = Field(
        default="",
        description="用户原文中指代字段的关键词，如 '年份'、'地区'；留空表示用户未显式提及字段",
    )
    original_value_keyword: str = Field(
        default="",
        description="用户原文中指代值的关键词，如 '北京'、'2024'；留空表示用户未显式提及值",
    )


class ConfirmedGroupBy(BaseModel):
    """确认后的 GROUP BY 项。"""

    field: str = Field(description="真实维度术语名")
    original_keyword: str = Field(default="", description="用户原文关键词，如 '班级'")


class ConfirmedOrderBy(BaseModel):
    """确认后的 ORDER BY 项。"""

    field: str = Field(description="真实术语名")
    direction: str = Field(default="ASC", description="排序方向: ASC / DESC")
    original_keyword: str = Field(default="", description="用户原文关键词，如 '平均分'")


class ConfirmedQuery(BaseModel):
    """LLM 确认后的查询：基于真实 schema 术语，标注需澄清项。

    LLM 根据召回结果：
    - 召回到完整复合度量 → 直接用作 SELECT（measure 直接取值）
    - 召回到原子度量 + 维度字段 → 重构为 SELECT（measure + agg_func + filters）
    - 多个候选无法区分 → 放入 clarify_items
    """

    select: list[ConfirmedSelectExpr] = Field(description="语义化 SELECT 列表")
    where: list[ConfirmedWhereClause] = Field(
        default_factory=list,
        description="WHERE 条件（含重构后新增的维度过滤）",
    )
    group_by: list[ConfirmedGroupBy] = Field(
        default_factory=list,
        description="GROUP BY 维度列表",
    )
    order_by: list[ConfirmedOrderBy] = Field(
        default_factory=list,
        description="ORDER BY 排序列表",
    )
    limit: int | None = Field(default=None)
    clarify_items: list[ClarifyItem] = Field(
        default_factory=list,
        description="需要用户澄清的项：多个候选无法区分，或召回为空",
    )
    needs_clarification: bool = Field(
        default=False,
        description="是否需要用户澄清。clarify_items 非空时为 True",
    )


# ── 语义 → SQL 还原 ──────────────────────────────────────────────────


def _build_case_condition(filters: list[DimensionFilter]) -> str:
    """将 DimensionFilter 列表构建为 SQL CASE WHEN 条件片段。"""
    parts: list[str] = []
    for f in filters:
        if isinstance(f.value, list):
            in_values = ", ".join(f"'{v}'" for v in f.value)
            parts.append(f"{f.dimension} IN ({in_values})")
        elif f.op == "=":
            parts.append(f"{f.dimension} = '{f.value}'")
        elif f.op == "!=":
            parts.append(f"{f.dimension} != '{f.value}'")
        elif f.op.upper() == "IN":
            parts.append(f"{f.dimension} IN ('{f.value}')")
        else:
            parts.append(f"{f.dimension} {f.op} '{f.value}'")
    return " AND ".join(parts)


def semantic_to_sql_expr(s: ConfirmedSelectExpr) -> str:
    """将语义化 SELECT 表达式还原为 SQL 表达式。

    还原规则：
    - 无 filters + 无 agg_func → 直接字段名
    - 无 filters + 有 agg_func → AGG(measure)
    - RATIO + 有 denominator → SUM(measure) / SUM(denominator) * 100
    - RATIO + 无 denominator + 有 filters → SUM(CASE WHEN ... THEN 1 ELSE 0 END) / COUNT(*) * 100
    - 有 filters + COUNT → SUM(CASE WHEN ... THEN 1 ELSE 0 END)
    - 有 filters + 其他 agg → AGG(CASE WHEN ... THEN measure ELSE NULL END)
    """
    agg = s.agg_func.upper().strip()
    has_filters = bool(s.filters)
    condition = _build_case_condition(s.filters) if has_filters else ""

    # RATIO: 比率计算
    if agg == "RATIO":
        return _build_ratio_sql(s.measure, s.denominator, condition, has_filters)

    # 非 RATIO、无 filters
    if not has_filters:
        return s.measure if not agg else f"{agg}({s.measure})"

    # 非 RATIO、有 filters
    if agg in ("COUNT", ""):
        return f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END)"
    return f"{agg}(CASE WHEN {condition} THEN {s.measure} ELSE NULL END)"


def _build_ratio_sql(
    measure: str,
    denominator: str,
    condition: str,
    has_filters: bool,
) -> str:
    """构建 RATIO 类型的 SQL 表达式。"""
    if denominator:
        numerator = (
            f"SUM(CASE WHEN {condition} THEN {measure} ELSE 0 END)"
            if has_filters
            else f"SUM({measure})"
        )
        return f"{numerator} / SUM({denominator}) * 100"
    # 计数占比
    if has_filters:
        return f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) / COUNT(*) * 100"
    return f"COUNT({measure}) / COUNT(*) * 100"


def semantic_to_display(s: ConfirmedSelectExpr) -> str:
    """将语义化 SELECT 表达式转为用户可读的展示文本。

    示例输出：
    - "度量[班级综合平均分（分）]"
    - "限定[成绩等级=优秀] → 度量[*] → 统计[RATIO]"
    - "度量[高新技术产值（万元）] / 分母[区域总产值（万元）] → 统计[RATIO]"
    """
    parts: list[str] = []

    if s.filters:
        filter_strs = []
        for f in s.filters:
            val = ", ".join(f.value) if isinstance(f.value, list) else str(f.value)
            filter_strs.append(f"{f.dimension}{f.op}{val}")
        parts.append(f"限定[{'; '.join(filter_strs)}]")

    if s.denominator:
        parts.append(f"度量[{s.measure}] / 分母[{s.denominator}]")
    else:
        parts.append(f"度量[{s.measure}]")

    if s.agg_func:
        parts.append(f"统计[{s.agg_func}]")

    return " → ".join(parts)


# ── Prompt ────────────────────────────────────────────────────────────

CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。根据知识库召回结果，将自然语言查询转为基于真实 schema 的结构化查询。

## 输入说明
- 用户原始查询和展开后的查询
- 每个关键词的知识库召回候选（候选名即真实字段名）
- 维度值线索：系统从短语中自动识别出的可能的维度过滤值（附所属维度和全部枚举值）

## SELECT 语义化结构

每个 SELECT 项必须拆解为以下结构化字段（不要写 SQL 表达式）：

- **measure**: 度量字段名（从候选中选择的真实术语名），或 "*" 表示计数
- **denominator**: 分母度量字段名（可选），非空时表示比率计算: measure / denominator
- **agg_func**: 聚合函数，可选值：SUM / COUNT / AVG / MIN / MAX / RATIO / ""（空串=直接取值）
  - RATIO 表示"占比/比率"语义：
    - 计数占比（denominator 为空）：条件计数 / 总数 × 100
    - 金额占比（denominator 非空）：SUM(measure) / SUM(denominator) × 100
- **filters**: 业务限定条件列表，每项包含 dimension（维度字段名）、op（运算符）、value（维度值）
  - 当关键词包含某个维度值的语义时（参考维度值线索），将其拆为 filter
- **original_keyword**: 用户原始说法
- **alias**: 展示别名（可选）

### 示例

用户说"优秀学生数"，维度值线索指出"优秀"→优秀(维度=成绩等级)：
```json
{
  "original_keyword": "优秀学生数",
  "measure": "*",
  "agg_func": "COUNT",
  "filters": [{"dimension": "成绩等级", "op": "=", "value": "优秀"}],
  "alias": "优秀学生数"
}
```

用户说"不及格占比"（计数占比，无分母），维度值线索指出"不及格"→不及格(维度=成绩等级)：
```json
{
  "original_keyword": "不及格占比",
  "measure": "*",
  "agg_func": "RATIO",
  "filters": [{"dimension": "成绩等级", "op": "=", "value": "不及格"}],
  "alias": "不及格占比"
}
```

用户说"竞赛获奖率"（金额/数量占比，有分母）：
```json
{
  "original_keyword": "竞赛获奖率",
  "measure": "竞赛获奖人数",
  "denominator": "参赛总人数",
  "agg_func": "RATIO",
  "filters": [],
  "alias": "竞赛获奖率"
}
```

用户说"班级平均分"，直接召回到字段：
```json
{
  "original_keyword": "班级平均分",
  "measure": "班级综合平均分（分）",
  "agg_func": "",
  "filters": [],
  "alias": "班级平均分"
}
```

用户说"平均语文成绩"：
```json
{
  "original_keyword": "平均语文成绩",
  "measure": "语文成绩（分）",
  "agg_func": "AVG",
  "filters": [],
  "alias": "平均语文成绩"
}
```

## 处理步骤

1. **确定 SELECT 字段**：从候选中选择最匹配的字段名作为 measure。如果关键词含有聚合语义（如"均值""总数""占比"），设置对应 agg_func。
2. **区分全局 WHERE 与度量级 filters**：
   判断标准：**该限定条件是否被所有 SELECT 项共享？**
   - **全局 WHERE**：限定条件对所有度量都生效（共享范围）→ 放 WHERE。
   - **度量级 filters**：限定条件只对部分度量生效（不同度量有不同限定）→ 放对应度量的 filters。
   - 如果查询只有一个 SELECT 项，则共享/不共享无区别，优先放 WHERE。
3. **确认 WHERE 字段**：用候选中的真实字段名替换用户原文中的自然语言字段名。每个 WHERE 项必须分别记录：
   - original_field_keyword：用户原文中指代字段的词（如"年份""地区"），用户没说则留空
   - original_value_keyword：用户原文中指代值的词（如"北京""2024"），用户没说则留空
4. **确认 GROUP BY**：每项必须带 field（真实字段名）和 original_keyword（用户原文）。
5. **确认 ORDER BY**：每项必须带 field（真实字段名）、direction（ASC/DESC）和 original_keyword（用户原文）。
6. **判断是否需要澄清**：多个候选无法区分、或召回为空时，放入 clarify_items，并标注 source 来源槽位。

### WHERE vs filters 示例

"各班级的优秀学生数和不及格占比"：
- "优秀" 只限定"学生数"（优秀学生数），不限定"不及格占比" → filters（在"学生数"的 SELECT 项上）
- "不及格" 只限定"占比"（不及格占比），不限定"学生数" → filters（在"占比"的 SELECT 项上）
- "班级" → GROUP BY

"三年级理科班的平均分和最高分"：
- "三年级" 同时限定"平均分"和"最高分" → WHERE
- "理科班" 同时限定两者 → WHERE
- 两个度量共享同一个范围，不需要 filters

## 关键规则
- 所有字段名和维度值**只能**来自召回候选或维度值线索，严禁编造不存在的名称
- **所有槽位都必须保留原始关键词追溯**：select/group_by/order_by 用 original_keyword；where 用 original_field_keyword + original_value_keyword（可分别留空）
- needs_clarification = true 当且仅当 clarify_items 非空
- clarify_items 中的 source 必须标明来源: "select" / "where" / "group_by" / "order_by"
- 候选列表中排在前面的通常更相关，但要结合语义判断
- 维度值线索是辅助参考，非已确认条件；高置信线索可直接采用，低置信的应放入 clarify_items
- **严禁在 measure/agg_func/filters 之外写 SQL 表达式**，所有计算逻辑必须通过这三个字段表达
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
        from .dimension_values import DimensionValueResolver

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
    recall_context: str,
    on_event: Callable[[Any], None] | None = None,
) -> ConfirmedQuery | None:
    """基于召回结果，调 LLM 生成真实 schema 的确认查询。

    Args:
        original_question: 用户原始查询。
        expanded_query: NatQuery 展开后的查询文本。
        recall_context: 外部构建的召回上下文文本。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        ConfirmedQuery 实例，LLM 失败时返回 None。
    """
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
        from .llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

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
