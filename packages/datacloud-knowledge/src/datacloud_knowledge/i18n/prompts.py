"""Locale-specific prompts and labels for datacloud-knowledge clarification.

Uses the same locale encoding as sibling package ``datacloud-analysis``:
``zh_CN`` / ``en_US`` (underscore, no hyphen).
"""

from __future__ import annotations

import os
from typing import Any

_FALLBACK_LOCALE = "zh_CN"

# ═════════════════════════════════════════════════════════════════════
# 1. LLM System Prompts
# ═════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPTS: dict[str, dict[str, str]] = {
    "zh_CN": {
        "main_legacy": """\
你是数据查询确认助手。根据知识库召回结果，将结构化查询中的中文术语映射到真实 schema 字段。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

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
- 如果召回候选第一名与原始术语语义高度匹配，直接确认，不需要澄清

## 维度建模一致性规则
- select / metrics 中的字段应来自相同粒度的数据实体
- 如果候选中有多个不同粒度的字段（如学生级 vs 班级级），优先选择与 \
dimensions / group_by 粒度一致的字段
- 例：dimensions 按"班级"分组，则 metrics 优先选班级级别的字段（如"班级平均分"）\
而非学生级别的字段（如"学生成绩"）
- 例：查询"各班级的语文平均分和数学平均分"，dimensions 是班级，\
metrics 应选班级级别的成绩字段而非学生级别的

## 粒度与查询对象匹配规则
- 候选精选时必须考虑查询对象的粒度：优先选择与查询对象同粒度的字段
- 如果用户查询的对象是"班级"，优先选择班级级汇总字段，而非学生级明细字段
- 如果用户查询的对象是"学生"，优先选择学生级字段，而非班级级汇总字段
- 例：查询"各班级语文平均分排名后3的班级"，候选有 ['语文期末成绩', '班级语文平均分', '数据来源']，\
应优先选 '班级语文平均分'（与"班级"粒度一致），而非 '语文期末成绩'（学生粒度）
- 例：查询"成绩排名前10的学生"，候选有 ['班级语文平均分', '学生语文期末成绩', '数据来源']，\
应优先选 '学生语文期末成绩'（学生粒度），而非 '班级语文平均分'（班级粒度）

## 数值与量化条件规则
- 纯数值（如 50、30%、100万、202602）直接保留原值，不需要召回确认
- 数值型 whereValue 的 confirmed 直接填原值，不标记为需澄清

## alias 引用规则
- order_by / having 中如果引用了 metrics[].as 别名，保持别名不变，不做翻译
- 如果 order_by.field 不是 metrics alias 引用，而是有对应的召回候选，则正常替换

## 保持原始结构规则
- limit / offset 保持原始输入的值，不做修改
- 不要增删原始结构中的字段数量，只做术语→真实字段名的替换
- filters 中已有的条件结构（field/op/value）保持不变，只替换 field 名为召回候选中的真实字段名
- filters.field 如果是英文编码（如 stat_date），且召回候选中有对应的中文字段名，替换为中文字段名

## complex_conditions 确认规则
- 对每条 NL 中的中文术语做确认
- 输出 original_term / start / end / confirmed / candidates
- 只有一个高置信候选 → confirmed 填值
- 多候选无法区分 → confirmed = null，candidates 按语义相关度降序排列
- candidates 必须精选：只保留与原始术语语义相关的候选（最多 5 个），\
过滤掉明显不相关的
- candidates 不能为空：即使没有精确匹配，也必须从召回候选中选出最接近的 2~3 个供用户选择。\
系统中的字段命名可能与用户术语不同（如用户说"道法"，系统字段叫"道德与法律"），\
这种情况下应将语义最近的候选保留，让用户判断
- candidates 仅从召回候选中选取，严禁编造
- 示例：术语"成绩"的召回候选为 ['数据来源', '语文期末成绩', '数学期末成绩', '统计日期', '班级平均分']，\
精选后 candidates = ['语文期末成绩', '数学期末成绩', '班级平均分']，\
过滤掉 '数据来源' 和 '统计日期'（与"成绩"语义无关）

## 关键规则
- needs_clarification = true ⟺ clarify_items 非空 或任何 complex_condition 术语的 confirmed 为 null
- clarify_items 中的 source 必须标明来源: "select" / "where" / "group_by" / "order_by"
- clarify_items 中的 candidates 必须按语义相关度降序排列，最多 5 个，过滤明显不相关项
- clarify_items 中的 candidates 必须全部来自召回候选，严禁编造
- 分析完成后必须调用工具提交结果，不要用文本回复

## 示例

用户查询: "查询语文成绩前10名的学生"
结构化输入（StructuredQuery）:
{
  "select": ["学生姓名", "语文成绩"],
  "order_by": [{"field": "语文成绩", "direction": "desc"}],
  "limit": 10
}
知识库召回结果:
== 查询值 ==
  学生姓名 (select): ['学生姓名', '学生学号', '班级名称']
  语文成绩 (select): ['语文期末成绩', '语文平时成绩', '数学期末成绩']
== 排序目标 ==
  语文成绩 (orderBy): ['语文期末成绩', '语文平时成绩', '数学期末成绩']

正确的工具调用参数:
{
  "select": ["学生姓名", "语文期末成绩"],
  "order_by": [{"field": "语文期末成绩", "direction": "desc"}],
  "limit": 10,
  "clarify_items": [],
  "needs_clarification": false
}
说明：学生姓名精确命中；语文成绩→语文期末成绩（排名第一且语义匹配）；limit=10 保持不变。

粒度匹配示例:
用户查询: "查询平均分排名后3的班级"
结构化输入: {"select": ["班级名称", "平均分"], "order_by": [{"field": "平均分", "direction": "asc"}], "limit": 3}
知识库召回结果:
== 查询值 ==
  班级名称 (select): ['班级名称', '班级编号', '学生姓名']
  平均分 (select): ['学生语文成绩', '班级语文平均分', '班级数学平均分', '学生数学成绩', '数据来源']
== 排序目标 ==
  平均分 (orderBy): ['学生语文成绩', '班级语文平均分', '班级数学平均分', '学生数学成绩', '数据来源']

正确的工具调用参数:
{
  "select": ["班级名称"],
  "order_by": [{"field": null, "direction": "asc"}],
  "limit": 3,
  "clarify_items": [
    {"keyword": "平均分", "candidates": ["班级语文平均分", "班级数学平均分"], "reason": "查询对象是班级，优先选班级粒度的字段；有多个班级级平均分需用户选择", "source": "select", "path": "/select/1"}
  ],
  "needs_clarification": true
}
说明：查询对象是"班级"，候选中"班级语文平均分"和"班级数学平均分"是班级粒度，\
"学生语文成绩"和"学生数学成绩"是学生粒度 → 过滤掉学生粒度的候选和无关的"数据来源"。

错误示例（不要这样做）:
- candidates 中出现 "语文综合成绩" ← 不在召回结果中，属于编造
- limit 被改为 null ← 不应修改原始值
- 用文本回复而不调用工具 ← 必须调用工具提交
""",
        "main": """\
你是数据查询确认助手。根据知识库召回结果，对待确认术语选择最匹配的候选。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

## 规则
- 对每个 #编号术语，从候选中选择语义最匹配的填入 confirmed
- 无法确定 → confirmed = null，candidates 填精选候选（最多5个），附 reason
- 重要：如果候选中没有与原始术语语义相关的字段，必须返回 confirmed = null，严禁强行选择不相关的候选
- candidates 不能为空：即使没有精确匹配，也必须从候选中选出最接近的 2~3 个供用户选择
- candidates 仅从召回候选中选取，严禁编造
- 标注"取值范围"的术语，confirmed 只能从取值范围中选取
- 已确认字段仅供理解上下文，不需要处理
- 候选列表中排在前面的通常更相关，但要结合语义判断
- 如果候选第一名与原始术语语义高度匹配，直接确认
- 纯数值（如 50、30%、100万、202602）直接保留原值
- needs_clarification = true ⟺ 任何术语 confirmed 为 null 且 candidates 非空
- 分析完成后必须调用工具提交结果，不要用文本回复

## 维度建模一致性规则
- select / metrics 中的字段应来自相同粒度的数据实体
- 如果候选中有多个不同粒度的字段，优先选择与 dimensions / group_by 粒度一致的字段

## 粒度与查询对象匹配规则
- 候选精选时必须考虑查询对象的粒度：优先选择与查询对象同粒度的字段
""",
        "cc": """\
你是数据查询确认助手。对条件句中的中文术语做映射。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

## 规则
- 对每个 #编号术语，从候选中选择语义最匹配的填入 confirmed
- 无法确定 → confirmed = null，candidates 填精选候选（最多5个），附 reason
- candidates 必须精选：只保留语义相关的候选，过滤明显不相关项
- candidates 不能为空：即使没有精确匹配，也必须从候选中选出最接近的 2~3 个
- candidates 仅从召回候选中选取，严禁编造
- 纯数值（30%、100）不需要映射，不会出现在待确认列表中
- needs_clarification = true ⟺ 任何术语 confirmed 为 null 且 candidates 非空
- 分析完成后必须调用工具提交结果，不要用文本回复
""",
    },
    "en_US": {
        "main_legacy": """\
You are a data query confirmation assistant. Based on knowledge base recall results, map the terms in the structured query to actual schema fields.
After analysis, you MUST call the tool to submit results — do NOT reply in text.

## Input
- User's original query
- Structured query parameters (StructuredQuery or StructuredCompute)
- Knowledge base recall candidates for each term
- Dimension value hints

## Main Structure Confirmation Rules
- All field names and dimension values must come from recall candidates or dimension value hints — fabrication is strictly forbidden
- Confirmed terms should be directly replaced with real field names
- Unresolved terms go into clarify_items with source and path
- Candidates listed first are usually more relevant, but always apply semantic judgment
- If the top candidate is a strong semantic match for the original term, confirm directly without clarification

## Dimensional Modeling Consistency Rules
- Fields in select/metrics should come from data entities at the same granularity level
- If candidates span multiple granularity levels (e.g., student-level vs. class-level), prefer candidates matching the dimensions/group_by granularity

## Numeric and Quantitative Condition Rules
- Pure numeric values (e.g., 50, 30%, 202602) keep the original value — no recall confirmation needed
- Numeric whereValue fields: fill confirmed with the original value; do NOT mark as requiring clarification

## Alias Reference Rules
- If order_by/having references a metrics[].as alias, keep the alias unchanged
- If order_by.field is NOT a metrics alias reference but has recall candidates, replace normally

## Structural Integrity Rules
- Keep limit/offset values unchanged from the original input
- Do NOT add or remove fields — only map terms to real field names
- Keep existing filter structures (field/op/value), only replace field names with recall candidates

## Complex Conditions Confirmation Rules
- Confirm terms in each NL condition sentence
- Output: original_term / start / end / confirmed / candidates
- Single high-confidence candidate → fill confirmed
- Multiple indistinguishable candidates → confirmed = null, candidates sorted by relevance (descending)
- candidates must be curated: keep only semantically relevant candidates (max 5), filter obviously irrelevant ones
- candidates must NOT be empty: even without exact matches, pick the closest 2–3 candidates from recall results
- candidates must come ONLY from recall results — fabrication is strictly forbidden

## Key Rules
- needs_clarification = true ⟺ clarify_items is non-empty OR any complex_condition term has confirmed = null
- clarify_items source must indicate origin: "select" / "where" / "group_by" / "order_by"
- clarify_items candidates must be sorted by relevance descending, max 5, filter irrelevant items
- All clarify_items candidates MUST come from recall results — fabrication is strictly forbidden
- After analysis, you MUST call the tool to submit results — do NOT reply in text

## Error Examples (do NOT do this):
- candidates contains a term NOT in recall results → this is fabrication
- limit is changed to null → do not modify original values
- Reply in text without calling the tool → you MUST call the tool
""",
        "main": """\
You are a data query confirmation assistant. Based on knowledge base recall results, select the best matching candidate for each term to be confirmed.
After analysis, you MUST call the tool to submit results — do NOT reply in text.

## Rules
- For each #numbered term, select the semantically best match from candidates and fill confirmed
- If uncertain → confirmed = null, candidates = curated list (max 5), with reason
- Important: if no candidate is semantically related to the original term, you MUST return confirmed = null — do NOT force-select an unrelated candidate
- candidates must NOT be empty: even without exact matches, pick the closest 2–3 candidates from recall results
- candidates must come ONLY from recall results — fabrication is strictly forbidden
- For terms marked with a value range, confirmed must be chosen ONLY from the value range
- Already-confirmed fields are for context only — do NOT process them
- Candidates listed first are usually more relevant, but always apply semantic judgment
- If the top candidate is a strong semantic match, confirm directly
- Pure numeric values keep the original value
- needs_clarification = true ⟺ any term has confirmed = null AND candidates is non-empty
- After analysis, you MUST call the tool to submit results — do NOT reply in text

## Dimensional Modeling Consistency Rules
- Fields in select/metrics should come from data entities at the same granularity level
- If candidates span multiple granularity levels, prefer candidates matching the dimensions/group_by granularity
""",
        "cc": """\
You are a data query confirmation assistant. Map terms in condition sentences to their canonical field names.
After analysis, you MUST call the tool to submit results — do NOT reply in text.

## Rules
- For each #numbered term, select the semantically best match from candidates and fill confirmed
- If uncertain → confirmed = null, candidates = curated list (max 5), with reason
- candidates must be curated: keep only semantically relevant candidates, filter obviously irrelevant ones
- candidates must NOT be empty: even without exact matches, pick the closest 2–3 candidates from recall results
- candidates must come ONLY from recall results — fabrication is strictly forbidden
- Pure numeric values (30%, 100) do NOT need mapping — they won't appear in the confirmation list
- needs_clarification = true ⟺ any term has confirmed = null AND candidates is non-empty
- After analysis, you MUST call the tool to submit results — do NOT reply in text
""",
    },
}

# ═════════════════════════════════════════════════════════════════════
# 2. Context Section Labels (confirm.py formatters)
# ═════════════════════════════════════════════════════════════════════

_CONTEXT_LABELS: dict[str, dict[str, Any]] = {
    "zh_CN": {
        # format_recall_context (line 193)
        "ktype_section_query": {
            "select": "查询值",
            "groupBy": "分组条件",
            "whereKey": "过滤条件（字段）",
            "whereValue": "过滤条件（值）",
            "orderBy": "排序目标",
        },
        # format_main_confirm_context (line 662)
        "ktype_section_main": {
            "select": "查询值",
            "groupBy": "分组条件",
            "whereKey": "过滤条件（字段）",
            "whereValue": "过滤条件（值）",
            "orderBy": "排序目标",
            "dimension": "维度",
            "metric": "指标",
        },
        # format_cc_confirm_context (line 840)
        "ktype_label_cc": {
            "select": "指标/字段",
            "groupBy": "分组",
            "whereKey": "过滤字段",
            "whereValue": "过滤值",
            "orderBy": "排序",
        },
        # Section headers
        "section_structured_input": "## 结构化输入（{mode}，上下文参考）",
        "section_confirmed": "## 已确认字段（仅供上下文，不需要处理）",
        "section_pending": "## 待确认术语",
        "section_no_pending": "## 无待确认术语（所有字段已确认）",
        "section_condition": "## 条件句",
        "section_submit": "## 请对每个编号术语确认并提交",
        # User prompt builder
        "user_query": "## 用户原始查询",
        "user_structured_input": "## 结构化输入（{mode}）",
        "user_recall": "## 知识库召回结果",
        "user_submit": "## 请确认并提交",
        "user_instruction": (
            "根据召回结果，将中文术语映射到真实 schema 字段，然后调用工具提交确认结果。"
        ),
        "no_recall_result": "无召回结果",
        "candidates": "候选",
        "enum_values": "取值范围",
        "source_tag_field_code": "field_code",
        "source_tag_alias_exact": "alias_exact",
    },
    "en_US": {
        "ktype_section_query": {
            "select": "Select",
            "groupBy": "Group By",
            "whereKey": "Filter (Field)",
            "whereValue": "Filter (Value)",
            "orderBy": "Order By",
        },
        "ktype_section_main": {
            "select": "Select",
            "groupBy": "Group By",
            "whereKey": "Filter (Field)",
            "whereValue": "Filter (Value)",
            "orderBy": "Order By",
            "dimension": "Dimension",
            "metric": "Metric",
        },
        "ktype_label_cc": {
            "select": "Metric/Field",
            "groupBy": "Group",
            "whereKey": "Filter Field",
            "whereValue": "Filter Value",
            "orderBy": "Sort",
        },
        "section_structured_input": "## Structured Input ({mode}, context)",
        "section_confirmed": "## Confirmed Fields (context only, no action needed)",
        "section_pending": "## Terms to Confirm",
        "section_no_pending": "## No Terms to Confirm (all fields confirmed)",
        "section_condition": "## Condition Sentence",
        "section_submit": "## Please confirm each numbered term and submit",
        "user_query": "## User Query",
        "user_structured_input": "## Structured Input ({mode})",
        "user_recall": "## Knowledge Base Recall Results",
        "user_submit": "## Please Confirm and Submit",
        "user_instruction": (
            "Based on recall results, map terms to actual schema fields, "
            "then submit using the tool."
        ),
        "no_recall_result": "No recall results",
        "candidates": "Candidates",
        "enum_values": "Value Range",
        "source_tag_field_code": "field_code",
        "source_tag_alias_exact": "alias_exact",
    },
}

# ═════════════════════════════════════════════════════════════════════
# 3. Paradigm Labels (cartesian.py build_paradigm_list)
# ═════════════════════════════════════════════════════════════════════

_PARADIGM_LABELS: dict[str, dict[str, str]] = {
    "zh_CN": {
        "1": "查询值",
        "2": "分组条件",
        "3": "过滤条件",
        "4": "排序目标",
        "5": "统计函数",
    },
    "en_US": {
        "1": "Select",
        "2": "Group By",
        "3": "Filter",
        "4": "Order By",
        "5": "Aggregation",
    },
}

# ═════════════════════════════════════════════════════════════════════
# 4. Annotation Format (cartesian.py _apply_replacements)
# ═════════════════════════════════════════════════════════════════════

_ANNOTATION_FORMATS: dict[str, str] = {
    "zh_CN": "（{text}）",  # full-width parentheses
    "en_US": " ({text})",  # half-width parentheses
}


# ═════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════


def _resolve_locale(locale: str | None) -> str:
    resolved = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)
    if resolved not in _SYSTEM_PROMPTS:
        return _FALLBACK_LOCALE
    return resolved


def get_confirm_prompt(locale: str | None = None, prompt_type: str = "main") -> str:
    """Return locale-specific LLM system prompt for term confirmation.

    Args:
        locale: ``"zh_CN"`` or ``"en_US"``. Falls back to env var
            ``DATACLOUD_AGENT_LOCALE``, then ``"zh_CN"``.
        prompt_type: ``"main"``, ``"cc"``, or ``"main_legacy"``.
    """
    resolved = _resolve_locale(locale)
    prompts = _SYSTEM_PROMPTS.get(resolved, _SYSTEM_PROMPTS[_FALLBACK_LOCALE])
    return prompts.get(prompt_type, prompts["main"])


def get_confirm_labels(locale: str | None = None) -> dict[str, Any]:
    """Return locale-specific context section labels for confirm formatters.

    Includes ktype section maps, section headers, and misc labels.
    """
    resolved = _resolve_locale(locale)
    return _CONTEXT_LABELS.get(resolved, _CONTEXT_LABELS[_FALLBACK_LOCALE])


def get_paradigm_labels(locale: str | None = None) -> dict[str, str]:
    """Return locale-specific paradigmName labels for clarification forms."""
    resolved = _resolve_locale(locale)
    return _PARADIGM_LABELS.get(resolved, _PARADIGM_LABELS[_FALLBACK_LOCALE])


def get_annotation_format(locale: str | None = None) -> str:
    """Return the locale-specific annotation format string.

    ``zh_CN`` → full-width parentheses ``"（{text}）"``.
    ``en_US`` → half-width parentheses ``" ({text})"``.
    """
    resolved = _resolve_locale(locale)
    return _ANNOTATION_FORMATS.get(resolved, _ANNOTATION_FORMATS[_FALLBACK_LOCALE])


def get_supported_locales() -> list[str]:
    """Return all supported locale codes."""
    return list(_SYSTEM_PROMPTS.keys())
