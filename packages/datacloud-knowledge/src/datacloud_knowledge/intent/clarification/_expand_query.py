"""NatQuery + expand_query — 提取自 natquery.py，供 clarification/extract.py 使用。

仅包含 expand_query 函数及其所需的最小依赖（NatQuery schema + SYSTEM_PROMPT）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────


class WhereClause(BaseModel):
    """WHERE 条件三元组。"""

    field: str = Field(description="字段名")
    field_alias: list[str] = Field(
        default_factory=list,
        description="字段名的同义别名列表",
    )
    op: str = Field(
        default="=",
        description="运算符: =, >, <, >=, <=, IN, BETWEEN, BOTTOM_PCT, TOP_PCT",
    )
    value: Any = Field(description="值，IN 时为列表")


class SelectExpr(BaseModel):
    """SELECT 表达式：字段引用或派生计算。"""

    expr: str = Field(description="字段引用或派生表达式")
    alias: list[str] = Field(
        default_factory=list,
        description="同义别名列表",
    )


class GroupByItem(BaseModel):
    """GROUP BY 维度。"""

    field: str = Field(description="分组维度名")
    field_alias: list[str] = Field(
        default_factory=list,
        description="维度名的同义别名列表",
    )


class NatQuery(BaseModel):
    """结构化查询：补全省略 + SQL 位置分类。"""

    query: str = Field(description="补全省略后的完整短语列表")
    select: list[SelectExpr] = Field(description="SELECT 表达式列表")
    where: list[WhereClause] = Field(default_factory=list, description="过滤条件")
    group_by: list[GroupByItem] = Field(default_factory=list, description="分组维度")
    order_by: list[str] = Field(default_factory=list, description="排序")
    limit: int | None = Field(default=None, description="行数限制")


# ── Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是语句省略补全与结构提取助手。

任务分两步：
1. 先按中文里的并列、省略、承前省略规则，把句中被省略但可以直接回填的词补全。
2. 再把补全后的结果整理成结构化查询。

## 一、怎样理解"省略补全"

在中文里，并列短语常共用后面的中心词或前面的修饰语，所以会出现省略。

例如：
- "语文、数学成绩的平均分、及格率"
  可以还原为：
  "语文成绩平均分、语文成绩及格率、数学成绩平均分、数学成绩及格率"

你的工作就是做这种"把原句里已经出现过、只是被省掉的部分补回去"的事情。

## 二、硬性规则

1. 只补全原句里已经出现、且能按语法直接回填的词。
2. 不得编造原句里没有出现过的类别、成员、专名或同义替换。
3. 如果用户只说"大类""各类""不同层次"等概括说法，但没有列出具体成员，不要自行枚举成员。
4. 如果原句已经明确列出并列成员，这些成员应逐一保留，不得合并成一个新短语，也不要随意改写成 where 或 group_by 中的筛选值。
5. 如果出现"甲、乙各X""甲、乙、丙各X"这类结构，前面的实例名通常是 X 的取值范围，应写入 where；X 本身写入 group_by。
6. query 是"补全层"结果：只能补回原句里已经出现、且可按语法直接回填的内容，不得造出原句没有的类别成员。
7. select / where / group_by 是"结构层"结果：可以为了结构化而使用规范化、SQL-like 的表达，但这些表达只能是对原句语义的整理，不能借机编造用户未提及的成员、类别或事实。
8. 允许猜测的是"schema 级规范字段名"，不允许猜测的是"成员、枚举值、实例名"。
   例如：
   - "用了多少电" → 可以规范成"用电量"这类字段名。
   - "各类级别" → 不可以自行猜成若干具体级别。
9. 如果一句话既可以少补全也可以多补全，优先选择"更保守、改动更少"的解释。

## 三、怎样区分"可补全的修饰语"和"具体值"

1. 可补全的修饰语：
   指并列结构里被共同省略、可以直接回填到多个短语中的词。
   例如"语文、数学成绩的平均分、及格率"里的"语文""数学""成绩"。

2. 具体值：
   指用户明确列出的实例名、专有名或可直接作为筛选值的内容。
   例如"甲班、乙班""上周""80分"。

3. 处理原则：
   - 可补全的修饰语，进入 query / select。
   - 并列列出的类别成员，如果共同修饰同一个中心词，也进入 query / select。
   - 明确的时间、阈值、实例名，进入 where。
   - 明确出现"各X""按X""分X"时，X 进入 group_by。
   - 只有在原句明确要求排序、前几名、后几名时，才填写 order_by / limit。
   - 当用户表达"前/后 X%"时，这是百分位过滤，不是行数截断。使用 where 条件，op 为 TOP_PCT（前X%）或 BOTTOM_PCT（后X%），value 为 0 到 1 的小数。例如"后30%"→ op="BOTTOM_PCT", value=0.3。不要写入 limit。

## 四、输出要求

- query：补全后的完整短语，使用"、"连接；这里只能做省略补全，不能补出原句没有的成员。
- select：与 query 对应；可以直接使用补全短语，也可以在必要时写成 SQL-like / 规范化表达。
  alias 用途：alias 和 expr 都会被用来做术语召回，所以请尽量为每个 SelectExpr 填写 alias，把你能想到的、用户可能的意思或同义说法放进去。
  同一个概念在数据库里可能有不同的字段名，alias 应尽量覆盖这些可能性。
  例如：用户说"用电最多的城市"，expr 可以写"用电量"，alias 写"城市用电量"；这样两种说法都能参与召回，提高命中率。
- where：只放原句明确给出的过滤条件。field_alias 列出该字段在数据库中可能的其他名称，提高召回命中率。
- group_by：只放原句明确要求的分组维度名。field_alias 列出该维度在数据库中可能的其他名称。
- order_by / limit：只放原句明确给出的排序和截断信息。

## 五、示例

<examples>
  <example>
    <doc>排序和截断来自原句明示；alias 填写同义说法提高召回</doc>
    <input>上周得分前五的小组</input>
    <output>
    {"query": "得分", "select": [{"expr": "得分", "alias": ["小组得分"]}], "where": [{"field": "时间", "field_alias": ["日期", "周"], "op": "=", "value": "上周"}], "group_by": [{"field": "小组", "field_alias": ["小组名称", "小组编号"]}], "order_by": ["得分 DESC"], "limit": 5}
    </output>
  </example>
  <example>
    <doc>并列省略补全：前后成分交叉组合</doc>
    <input>各班语文、数学成绩的平均分、及格率</input>
    <output>
    {"query": "语文成绩平均分、语文成绩及格率、数学成绩平均分、数学成绩及格率", "select": [{"expr": "语文成绩平均分"}, {"expr": "语文成绩及格率"}, {"expr": "数学成绩平均分"}, {"expr": "数学成绩及格率"}], "where": [], "group_by": [{"field": "班级", "field_alias": ["班级名称", "班号"]}], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>已明确列出的并列成员，保留在 query / select 中</doc>
    <input>春季、秋季课程的报名人数、通过率</input>
    <output>
    {"query": "春季课程报名人数、春季课程通过率、秋季课程报名人数、秋季课程通过率", "select": [{"expr": "春季课程报名人数"}, {"expr": "春季课程通过率"}, {"expr": "秋季课程报名人数"}, {"expr": "秋季课程通过率"}], "where": [], "group_by": [], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>实例名进入 where，分组维度来自"各X"</doc>
    <input>上周甲班、乙班各题型得分超过80分的人数</input>
    <output>
    {"query": "人数", "select": [{"expr": "人数", "alias": ["答题人数"]}], "where": [{"field": "时间", "field_alias": ["日期"], "op": "=", "value": "上周"}, {"field": "班级", "field_alias": ["班级名称"], "op": "IN", "value": ["甲班", "乙班"]}, {"field": "得分", "field_alias": ["分数", "成绩"], "op": ">", "value": "80分"}], "group_by": [{"field": "题型", "field_alias": ["题目类型"]}], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>并列成员逐一展开，不合并成一个短语</doc>
    <input>短篇、长篇文章的字数、页数</input>
    <output>
    {"query": "短篇文章字数、短篇文章页数、长篇文章字数、长篇文章页数", "select": [{"expr": "短篇文章字数"}, {"expr": "短篇文章页数"}, {"expr": "长篇文章字数"}, {"expr": "长篇文章页数"}], "where": [], "group_by": [], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>未列出具体成员时，不自行枚举</doc>
    <input>各年级作品分布</input>
    <output>
    {"query": "作品分布", "select": [{"expr": "作品分布", "alias": ["作品数量"]}], "where": [], "group_by": [{"field": "年级", "field_alias": ["年级名称"]}], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>派生计算来自原句明示</doc>
    <input>各班优秀人数占总人数的比例</input>
    <output>
    {"query": "优秀人数、总人数、优秀占比", "select": [{"expr": "优秀人数"}, {"expr": "总人数"}, {"expr": "优秀人数 / 总人数", "alias": ["优秀占比", "优秀率"]}], "where": [], "group_by": [{"field": "班级", "field_alias": ["班级名称"]}], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>query 保持补全，结构层允许规范化表达</doc>
    <input>上周甲班、乙班作文得分的平均分</input>
    <output>
    {"query": "作文得分平均分", "select": [{"expr": "AVG(作文得分)", "alias": ["作文得分平均分", "作文平均分"]}], "where": [{"field": "时间", "op": "=", "value": "上周"}, {"field": "班级", "op": "IN", "value": ["甲班", "乙班"]}], "group_by": [], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>百分位过滤用 BOTTOM_PCT/TOP_PCT，不用 limit</doc>
    <input>成绩排名后20%的学生</input>
    <output>
    {"query": "学生", "select": [{"expr": "学生", "alias": ["学生姓名", "学生编号"]}], "where": [{"field": "成绩", "field_alias": ["考试成绩", "总成绩"], "op": "BOTTOM_PCT", "value": 0.2}], "group_by": [], "order_by": [], "limit": null}
    </output>
  </example>
</examples>
"""


# ── 公共 API ─────────────────────────────────────────────────────────


def expand_query(
    query: str,
    on_event: Callable[[Any], None] | None = None,
) -> NatQuery | None:
    """调用 LLM 将自然语言查询展开为 NatQuery 结构。

    Args:
        query: 用户原始自然语言查询。
        on_event: 可选回调，接收 StreamEvent 实例。

    Returns:
        NatQuery 实例，LLM 调用失败时返回 None。
    """
    from datacloud_knowledge.intent.llm_utils import (
        build_llm,
        extract_json_from_text,
        stream_invoke_with_thinking,
    )

    try:
        llm = build_llm()
        llm_with_tool = llm.bind_tools(
            [NatQuery],
        )
        response = stream_invoke_with_thinking(
            llm_with_tool,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            on_event=on_event,
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            logger.info(
                "[natquery] LLM expand ok: %s",
                json.dumps(args, ensure_ascii=False),
            )
            return NatQuery.model_validate(args)

        # 兜底：从 content 文本中提取 JSON
        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[natquery] LLM 未返回 tool call，尝试从文本提取 JSON")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            logger.info(
                "[natquery] 兜底提取成功: %s",
                json.dumps(fallback, ensure_ascii=False),
            )
            return NatQuery.model_validate(fallback)
        logger.warning("[natquery] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[natquery] LLM 调用失败")
    return None
