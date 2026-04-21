"""Agent-side schema description overrides for query/compute tools.

这些常量是面向 LLM 的工具参数说明（tool 级别），与 i18n/prompts.py
中的 ReAct 执行规则（agent 级别）位于不同抽象层，不应混放。
"""

AGENT_SELECT_DESCRIPTION: str = (
    "返回字段列表；支持字段编码（如 'enterprise_name'）或字段中文名（如 '企业名称'）；"
    "找不到精确对应时直接填用户原词，禁止猜测替换为相近字段名；"
    "为空时返回全部非关联字段。"
)

AGENT_ORDER_BY_FIELD_DESCRIPTION: str = (
    "字段编码（如 'total_revenue'）或字段中文名（如 '总营收'）；"
    "找不到精确对应时直接填用户原词，禁止猜测替换为相近字段名。"
)

AGENT_COMPLEX_CONDITIONS_DESCRIPTION: str = (
    "溢出过滤区：仅当**过滤值在填参时无法确定为字面常量**时，将该条件片段用自然语言写入此列表。\n"
    "触发场景：\n"
    "1. 相对排名（如'后30%'、'前N名'）；\n"
    "2. 跨对象子查询（如'亩产效益后30%的地块'作为过滤范围）；\n"
    "3. 动态比较值（如'高于行业平均'）。\n"
    "⚠️ 字段名在字段列表中找不到时，不写入此列表——直接在 select/filters/order_by 中填原词。\n"
    "字段名透传与 complex_conditions 是两个独立规则，不能混用。\n"
    "写入内容：只写无法字面化的那个条件片段，不写整句查询。\n"
    "此列表非空时系统自动路由到全能查询路径（data_query），无需手动调用。"
)
