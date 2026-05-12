"""Agent-side schema description overrides for query/compute tools.

这些常量是面向 LLM 的工具参数说明（tool 级别），与 i18n/prompts.py
中的 ReAct 执行规则（agent 级别）位于不同抽象层，不应混放。
"""

# Bilingual backup (zh+en):
# AGENT_QUERY_DESCRIPTION: str = (
#     "[Required] Complete natural-language description of the user's original query intent. "
#     "Used for intent classification, complex-query routing, and fallback inference when parameters are missing. "
#     "【必填】用户原始查询意图的完整自然语言描述。"
#     "用于意图分类记录、复杂查询路由及参数缺失时的兜底推断。"
# )
AGENT_QUERY_DESCRIPTION: str = (
    "[Required] Complete natural-language description of the user's original query intent. "
    "Used for intent classification, complex-query routing, and fallback inference when parameters are missing."
)

AGENT_SELECT_DESCRIPTION: str = (
    "【必填】返回字段列表，至少填一个字段；"
    "支持字段编码（如 'enterprise_name'）或字段中文名（如 '企业名称'）；"
    "找不到精确对应时直接填用户原词，禁止猜测替换为相近字段名；"
    "禁止留空——用户未指定时，根据查询意图从字段列表中选取最相关的字段。"
)

AGENT_ORDER_BY_FIELD_DESCRIPTION: str = (
    "字段编码（如 'total_revenue'）或字段中文名（如 '总营收'）；"
    "找不到精确对应时直接填用户原词，禁止猜测替换为相近字段名。"
)

# Bilingual backup (zh+en):
# AGENT_COMPLEX_CONDITIONS_DESCRIPTION: str = (
#     "Overflow filter zone: write a condition fragment here in natural language ONLY when the filter value "
#     "cannot be determined as a literal constant at parameter-fill time.\n"
#     "Trigger scenarios:\n"
#     "1. Relative ranking (e.g. 'bottom 30%', 'top N');\n"
#     "2. Cross-object sub-query (e.g. 'plots whose yield-efficiency is in the bottom 30%' as a filter range);\n"
#     "3. Dynamic comparison value (e.g. 'above industry average').\n"
#     "⚠️ If a field name is not found in the field list, do NOT write it here — pass it as-is in select/filters/order_by.\n"
#     "Field pass-through and complex_conditions are two independent rules; do not mix them.\n"
#     "Write only the non-literalisable condition fragment, not the full query sentence.\n"
#     "When this list is non-empty the system automatically routes to the full-capability query path (data_query); no manual call needed.\n"
#     "溢出过滤区：仅当**过滤值在填参时无法确定为字面常量**时，将该条件片段用自然语言写入此列表。\n"
#     "触发场景：\n"
#     "1. 相对排名（如'后30%'、'前N名'）；\n"
#     "2. 跨对象子查询（如'亩产效益后30%的地块'作为过滤范围）；\n"
#     "3. 动态比较值（如'高于行业平均'）。\n"
#     "⚠️ 字段名在字段列表中找不到时，不写入此列表——直接在 select/filters/order_by 中填原词。\n"
#     "字段名透传与 complex_conditions 是两个独立规则，不能混用。\n"
#     "写入内容：只写无法字面化的那个条件片段，不写整句查询。\n"
#     "此列表非空时系统自动路由到全能查询路径（data_query），无需手动调用。"
# )
AGENT_COMPLEX_CONDITIONS_DESCRIPTION: str = (
    "Overflow filter zone: write a condition fragment here in natural language ONLY when the filter value "
    "cannot be determined as a literal constant at parameter-fill time.\n"
    "Trigger scenarios:\n"
    "1. Relative ranking (e.g. 'bottom 30%', 'top N');\n"
    "2. Cross-object sub-query (e.g. 'plots whose yield-efficiency is in the bottom 30%' as a filter range);\n"
    "3. Dynamic comparison value (e.g. 'above industry average').\n"
    "⚠️ If a field name is not found in the field list, do NOT write it here — pass it as-is in select/filters/order_by.\n"
    "Field pass-through and complex_conditions are two independent rules; do not mix them.\n"
    "Write only the non-literalisable condition fragment, not the full query sentence.\n"
    "When this list is non-empty the system automatically routes to the full-capability query path (data_query); no manual call needed."
)
