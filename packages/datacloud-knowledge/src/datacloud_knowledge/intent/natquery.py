"""NatQuery — NatSQL 风格查询展开与结构化。

核心能力：
1. NatQuery Pydantic schema（SQL 位置语义 + 自然语言字段名）
2. 系统提示词 + 跨域 few-shot 示例
3. NatQuery → 五段式转换（兼容现有 paradigm 协议）
4. LLM 调用入口（懒导入 langchain，不增加硬依赖）

调用方式：
    from datacloud_knowledge.intent.natquery import expand_query
    result = expand_query("202602龙头、骨干企业的数量、营收")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────


class WhereClause(BaseModel):
    """WHERE 条件三元组。"""

    field: str = Field(description="字段名")
    op: str = Field(default="=", description="运算符: =, >, <, >=, <=, IN, BETWEEN")
    value: Any = Field(description="值，IN 时为列表")


class SelectExpr(BaseModel):
    """SELECT 表达式：字段引用或派生计算。"""

    expr: str = Field(description="字段引用或派生表达式")
    alias: str = Field(default="", description="别名，派生计算时必填")


class NatQuery(BaseModel):
    """NatSQL 风格查询：先展开，再结构化。

    重要：数据仓库中，"龙头企业营收"可能是一个预计算的汇总度量字段，
    而不是通过 WHERE 企业类型='龙头' 过滤后聚合得到的。
    因此必须先将查询展开为完整的度量短语，再写入 SELECT。
    """

    query: str = Field(
        description=(
            "第一步：将用户查询中的笛卡尔积展开为完整的度量短语列表。"
            "例如：'龙头、骨干企业的数量、营收' → "
            "'龙头企业数量、龙头企业营收、骨干企业数量、骨干企业营收'。"
            "展开原因：数据库中可能没有'企业类型'维度，只有'龙头企业数量'这样的预计算汇总字段，"
            "只有用完整短语才能匹配到这些字段。"
        )
    )
    select: list[SelectExpr] = Field(
        description=(
            "第二步：基于 query 中展开后的短语，写入 SELECT。"
            "每个展开后的完整短语对应一个 SelectExpr。"
        )
    )
    where: list[WhereClause] = Field(
        default_factory=list,
        description="过滤条件：时间、数值阈值、地域、状态等",
    )
    group_by: list[str] = Field(
        default_factory=list,
        description="分组维度：'各街道'→['街道']。注意：已展开进 SELECT 的类别不要再放 GROUP BY",
    )
    order_by: list[str] = Field(
        default_factory=list,
        description="排序，如'营收 DESC'",
    )
    limit: int | None = Field(default=None, description="行数限制")


# ── Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是 NatSQL 查询生成器。将用户自然语言转成结构化查询，使用自然语言作为字段名。

## 为什么要展开

数据仓库中，很多度量是预计算的汇总字段，而非通过维度过滤+聚合得到的。例如：
- 数据库可能有 "本科毕业人数" 这个字段，但没有 "学历层次" 维度可供 GROUP BY
- 数据库可能有 "线上渠道总销售额" 字段，但没有 "渠道类型" 维度
- 如果写 GROUP BY 学历层次，查不到任何东西；只有用完整短语 "本科毕业人数" 才能匹配

因此，必须先把用户查询中的类别×指标展开为完整短语，再逐一写入 SELECT，不要用 GROUP BY 替代展开。

## 规则

1. query 字段：先将笛卡尔积完全展开为完整短语列表
2. select：基于 query 展开结果，每个完整短语写一个 SelectExpr
3. 已展开进 select 的类别（如龙头/骨干）不要再放入 GROUP BY 或 WHERE
4. WHERE 只放真正的过滤条件：时间、数值阈值、经营状态、风险等级、地域等
5. 派生计算（占比、同比）用表达式 + alias

<examples>
  <example>
    <doc>简单查询：单指标 + 过滤</doc>
    <input>司龄5年以上的员工有多少人？</input>
    <output>
    {"query": "员工人数", "select": [{"expr": "员工人数"}], "where": [{"field": "司龄", "op": ">", "value": "5年"}], "group_by": [], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>分组 + 多条件过滤 + 阈值</doc>
    <input>广东省上半年GDP总数大于1万的地市</input>
    <output>
    {"query": "GDP总数", "select": [{"expr": "GDP总数"}], "where": [{"field": "时间", "op": "=", "value": "上半年"}, {"field": "省份", "op": "=", "value": "广东省"}, {"field": "GDP", "op": ">", "value": "1万"}], "group_by": ["地市"], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>排序 + 截断</doc>
    <input>第二季度北美苹果手机出货量前五的国家</input>
    <output>
    {"query": "苹果手机出货量", "select": [{"expr": "苹果手机出货量"}], "where": [{"field": "时间", "op": "=", "value": "第二季度"}, {"field": "地区", "op": "=", "value": "北美"}], "group_by": ["国家"], "order_by": ["苹果手机出货量 DESC"], "limit": 5}
    </output>
  </example>
  <example>
    <doc>笛卡尔展开：2类别×3指标=6个度量</doc>
    <input>各部门正式、实习员工的人数、平均薪资、总加班时长</input>
    <output>
    {"query": "正式员工人数、正式员工平均薪资、正式员工总加班时长、实习员工人数、实习员工平均薪资、实习员工总加班时长", "select": [{"expr": "正式员工人数"}, {"expr": "正式员工平均薪资"}, {"expr": "正式员工总加班时长"}, {"expr": "实习员工人数"}, {"expr": "实习员工平均薪资"}, {"expr": "实习员工总加班时长"}], "where": [], "group_by": ["部门"], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>笛卡尔展开 + 过滤条件：展开类别不进 WHERE</doc>
    <input>各校区本科、硕士、博士在读人数和毕业人数</input>
    <output>
    {"query": "本科在读人数、本科毕业人数、硕士在读人数、硕士毕业人数、博士在读人数、博士毕业人数", "select": [{"expr": "本科在读人数"}, {"expr": "本科毕业人数"}, {"expr": "硕士在读人数"}, {"expr": "硕士毕业人数"}, {"expr": "博士在读人数"}, {"expr": "博士毕业人数"}], "where": [], "group_by": ["校区"], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>笛卡尔展开 + 过滤 + 统计语义折叠</doc>
    <input>上半年各门店线上、线下渠道的总销售额、平均客单价</input>
    <output>
    {"query": "线上渠道总销售额、线上渠道平均客单价、线下渠道总销售额、线下渠道平均客单价", "select": [{"expr": "线上渠道总销售额"}, {"expr": "线上渠道平均客单价"}, {"expr": "线下渠道总销售额"}, {"expr": "线下渠道平均客单价"}], "where": [{"field": "时间", "op": "=", "value": "上半年"}], "group_by": ["门店"], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>三层笛卡尔展开：2×2×1=4个度量</doc>
    <input>各区县公立、私立医院的门诊、住院人次</input>
    <output>
    {"query": "公立医院门诊人次、公立医院住院人次、私立医院门诊人次、私立医院住院人次", "select": [{"expr": "公立医院门诊人次"}, {"expr": "公立医院住院人次"}, {"expr": "私立医院门诊人次"}, {"expr": "私立医院住院人次"}], "where": [], "group_by": ["区县"], "order_by": [], "limit": null}
    </output>
  </example>
  <example>
    <doc>派生计算：占比表达式</doc>
    <input>各地区A类商品销售额占总销售额的比例</input>
    <output>
    {"query": "A类商品销售额、总销售额、A类商品占比", "select": [{"expr": "A类商品销售额"}, {"expr": "总销售额"}, {"expr": "A类商品销售额 / 总销售额", "alias": "A类商品占比"}], "where": [], "group_by": ["地区"], "order_by": [], "limit": null}
    </output>
  </example>
</examples>
"""


# ── NatQuery → 五段式转换 ─────────────────────────────────────────────

_OP_MAP: dict[str, str] = {
    "=": "eq",
    ">": "gt",
    "<": "lt",
    ">=": "gte",
    "<=": "lte",
}


def natquery_to_five_stage(nq: NatQuery) -> dict[str, Any]:
    """将 NatQuery 转换为现有五段式格式，兼容 paradigm 下游全链路。

    映射关系：
        select   → query_target (paradigmId=1)
        group_by → group_by     (paradigmId=2)
        where    → filter_condition (paradigmId=3)
        order_by → order_by     (paradigmId=4)
        统计函数 → []           (paradigmId=5, 已折叠进 select)
    """
    # select → query_target（非派生表达式的 expr）
    query_target: list[str] = [s.expr for s in nq.select if not s.alias]

    # where → filter_condition（按 field 分组）
    filter_condition: dict[str, list[str]] = {}
    for w in nq.where:
        op_prefix = _OP_MAP.get(str(w.op), str(w.op))
        if isinstance(w.value, list):
            filter_condition.setdefault(w.field, []).extend(
                str(v) for v in w.value
            )
        elif op_prefix == "eq" or w.op == "=":
            filter_condition.setdefault(w.field, []).append(str(w.value))
        else:
            filter_condition.setdefault(w.field, []).append(
                f"{w.op}{w.value}"
            )

    return {
        "query": nq.query,
        "query_target": query_target,
        "group_by": list(nq.group_by),
        "filter_condition": filter_condition,
        "order_by": list(nq.order_by),
        "agg_function": [],
    }


# ── 公共 API ─────────────────────────────────────────────────────────


def expand_query(query: str) -> NatQuery | None:
    """调用 LLM 将自然语言查询展开为 NatQuery 结构。

    Args:
        query: 用户原始自然语言查询。

    Returns:
        NatQuery 实例，LLM 调用失败时返回 None。
    """
    from .llm_utils import build_llm, extract_json_from_text  # noqa: PLC0415

    try:
        llm = build_llm()
        llm_with_tool = llm.bind_tools([NatQuery], tool_choice="NatQuery")
        response = llm_with_tool.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ])
        if response.tool_calls:
            args = response.tool_calls[0]["args"]
            logger.info(
                "[natquery] LLM expand ok: %s",
                json.dumps(args, ensure_ascii=False),
            )
            return NatQuery.model_validate(args)

        # 兜底：从 content 文本中提取 JSON（MiniMax reasoning 模式偶发 tool call 失败）
        content = response.content if hasattr(response, "content") else str(response)
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
