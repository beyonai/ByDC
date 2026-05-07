"""Provide locale-specific system prompts for DataCloud agent.

虚拟工具前缀（query_/compute_）由 ``datacloud_data_service.config.Settings``
配置决定，可通过环境变量 ``DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX`` /
``DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX`` 覆盖。
"""

from __future__ import annotations

import os

from datacloud_data_service.config import get_settings


def _virtual_prefixes() -> tuple[str, str]:
    """返回 (query_prefix, compute_prefix)，与工具生成层共享同一配置源。"""
    s = get_settings()
    return s.virtual_action_query_prefix, s.virtual_action_compute_prefix


def _bare_prefix(prefix: str) -> str:
    """剥离尾部下划线，得到提示词中"裸名"形态；前缀本身无下划线时原样返回。"""
    return prefix.rstrip("_") if prefix.endswith("_") else prefix


_SYSTEM_PROMPTS: dict[str, str] = {
    "zh_CN": (
        "你是 DataCloud 数据分析助手，负责帮助用户完成数据分析与业务洞察。\n\n"
        "## 工具使用规则\n"
        "- 当用户询问业务数据（如商机、客户、订单、成交或任意业务记录）时，"
        "应优先使用当前 Agent 已挂载的动态查询工具，不要转交给子代理。\n"
        "- 对自然语言数据分析问题，优先选择最匹配的动态查询工具。\n"
        "- 请用中文回答，表达简洁、准确。"
    ),
    "en_US": (
        "You are a DataCloud data analysis assistant. \n\n"
        "- Please respond in concise and accurate English."
    ),
}


_FALLBACK_LOCALE = "zh_CN"


def _get_query_tool_hint_zh() -> str:
    """返回统一查询工具命名规则提示（前缀由 Settings 决定）。"""
    q, c = _virtual_prefixes()
    qb, cb = _bare_prefix(q), _bare_prefix(c)
    return (
        "## 查询工具命名规则\n"
        f"- 查询工具名称格式为 {q}{{对象编码}}（如 {q}ads_enterprise_analysis），"
        f"聚合计算工具格式为 {c}{{对象编码}}（如 {c}ads_enterprise_analysis）。\n"
        "- 复杂查询（complex_conditions 非空）系统后端自动处理，agent 无需手动调用其他工具。\n"
        f"- 禁止调用不含对象编码的裸工具名（如直接调用 {qb} 或 {cb}）。\n"
    )


def _get_query_tool_hint_en() -> str:
    """Return query tool naming hint with prefixes resolved from Settings."""
    q, c = _virtual_prefixes()
    qb, cb = _bare_prefix(q), _bare_prefix(c)
    return (
        "## Query tool naming\n"
        f"- Tool format: {q}{{object_code}} (e.g. {q}ads_enterprise_analysis), "
        f"{c}{{object_code}} (e.g. {c}ads_enterprise_analysis).\n"
        "- Complex queries (complex_conditions non-empty) are handled automatically by the backend.\n"
        f"- Do NOT call bare names like '{qb}' or '{cb}' without the object suffix.\n"
    )


def _disable_ask_user_tool() -> bool:
    """Match ``execution/node.py``: when True, builtin ``ask_user`` is not mounted."""

    return os.environ.get("DATACLOUD_DISABLE_ASK_USER_TOOL", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def get_system_prompt(locale: str | None = None) -> str:
    """Return locale-specific system prompt with fallback support."""

    resolved_locale_raw = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)

    resolved_locale = resolved_locale_raw or _FALLBACK_LOCALE

    return _SYSTEM_PROMPTS.get(resolved_locale, _SYSTEM_PROMPTS[_FALLBACK_LOCALE])


def get_supported_locales() -> list[str]:
    """Return all supported locale codes."""

    return list(_SYSTEM_PROMPTS.keys())


def _build_exec_zh() -> str:
    no_ask = _disable_ask_user_tool()
    parts = [
        "## 执行规则\n",
        "- 你具备工具调用能力，请通过工具完成用户任务。\n",
        "- 分析结束时必须调用 finish_react 工具提交最终答案，禁止直接输出。\n",
        "- 工具返回中包含 _hint 字段时，必须立即按照 _hint 指示调用 finish_react，禁止将数据整理为文字回复。\n",
    ]
    if not no_ask:
        parts.append("- 仅当问题含义不清或工具明确要求追问时，才使用 ask_user（详见下方规则）。\n")
    else:
        parts.append(
            "- 当前未挂载 ask_user 工具：禁止试图调用 ask_user。"
            "若需用户补充信息，请直接调用 finish_react（result_type=text）"
            "在 answer 中用中文写清楚需要用户提供什么。\n"
        )
    parts.extend(
        [
            "- 每次工具调用必须填写 reason 字段，说明选择该工具的理由。\n",
            "- 工具返回 [工具调用失败] 时，必须分析错误原因并用正确参数重新调用该工具，禁止直接调用 finish_react 放弃。\n",
        ]
    )
    # 插入模式感知的查询工具命名提示
    query_tool_hint = _get_query_tool_hint_zh()
    if query_tool_hint:
        parts.append(query_tool_hint)
    if not no_ask:
        parts.extend(
            [
                "## ask_user 使用规则（重要）\n",
                "- ask_user 工具只能用于以下情形：\n",
                "  1. 用户问题本身含义不清，无法确定要查什么数据；\n",
                "  2. 查询工具返回 result_type=ask_user，要求追问用户。\n",
                "- 禁止将 ask_user 用于礼貌性确认，例如询问是否需要进一步分析或其他帮助。\n",
                "- 查询工具成功返回数据后，应直接调用 finish_react，不得再询问用户。\n",
            ]
        )
    else:
        parts.append("- 查询工具成功返回数据后，应直接调用 finish_react，不得再试图追问用户。\n")

    ask_user_result_line = (
        "- 如果 result_type=ask_user，需要向用户追问，使用 ask_user 工具。\n"
        if not no_ask
        else (
            "- 如果 result_type=ask_user 或接口要求追问用户："
            "未挂载追问工具，请调用 finish_react（result_type=text）"
            "并在 answer 中写出要问用户的内容，勿再试图调用 ask_user。\n"
        )
    )
    q, c = _virtual_prefixes()
    parts.extend(
        [
            "## compute 统计工具参数规则\n",
            f"- 调用 {c}{{对象编码}} 时，`metrics` 数组每项必须包含：`field`（字段中文名如'企业总营收（万元）'或字段编码如 total_revenue，系统自动识别映射）、"
            "**`agg`**（聚合名，如 count、sum、count_distinct）、`as`（结果列别名）。\n",
            "- metrics 和 dimensions 中指定字段使用 `field` 键，可填中文名或字段编码，系统自动映射。\n",
            "- 禁止使用 `func` 作为聚合键名；协议与校验只识别 **`agg`**。\n",
            "## 查询工具参数规则\n",
            "- 调用数据查询工具时，query 参数必须是完整的自然语言问题，描述用户真正想查询的内容，例如「查询企业分析表的全部字段」。\n",
            "- 禁止使用 *、%、ALL 等通配符或占位符作为 query 参数。\n",
            "- 如果用户原始问题较短，应结合上下文将其改写为完整、清晰的自然语言查询。\n",
            "## 工具选择引导\n",
            "- 调用工具前，先在心中完成贪心预判：\n",
            f"  1. 目标对象：从问题中识别要查询的本体（如'企业'→{q}enterprise_view）。\n",
            f"  2. 任务类型：明细查询 → {q}*；统计聚合 → {c}*。\n",
            "  3. 参数预填：对照工具描述中的字段能力表，提前确定 select/filters/dimensions/metrics。\n",
            f"## {q}*/{c}* 核心参数规则\n",
            "- **query（必填）**：完整自然语言问题，不得为空，不得使用 */%/ALL 等通配符。\n",
            "  如用户原始问题较短，结合上下文改写为完整清晰的查询描述。\n",
            "- **标准参数**（select / filters / dimensions / metrics）：\n",
            "  填写时可使用 field_code 或中文字段名，系统自动映射；不确定时留空，结合 query 自动推断。\n",
            "  filters 的 value 只填字面常量（已知的具体数值、日期、枚举值）。\n",
            "  ⚠️ **字段名不存在时必须透传原词**：若某个词（如'贡献率'、'地块'）在工具的字段列表中\n",
            "  找不到精确对应，禁止猜测替换为相近字段名；必须将用户的原始词直接填入对应参数\n",
            "  （如 select: ['贡献率']、order_by: [{'field': '贡献率', 'direction': 'asc'}]），\n",
            "  系统后端会做语义解析。字段透传与 complex_conditions 是独立规则，互不影响。\n",
            "- **complex_conditions（溢出过滤区）**：\n",
            "  满足以下条件时，必须将该条件用自然语言写入此列表：\n",
            "  1. 过滤条件的值在填参时无法确定为字面常量（如'后30%'、'高于平均'、'排名前10名'）。\n",
            "  ⚠️ 字段名在字段列表中找不到时，不触发 complex_conditions——直接透传原词到标准参数即可。\n",
            "  示例：'亩产效益后30%的地块'、'营收高于行业平均值'。\n",
            "  此列表非空时系统后端自动路由到全能查询路径，无需手动调用其他工具。\n",
            "- **禁止**：同时将同一条件既写入 filters 又写入 complex_conditions。\n",
            "## 查询工具返回结构规则\n",
            f"- {q}*/{c}* 返回结构：{{data: {{result_type, records, file: {{file_url}}, meta}}}}。\n",
            "- 如果返回中包含 file_url 字段或顶层 _hint 字段，说明数据已存入本地文件，直接使用该文件路径。\n",
            "- 如果 result_type=rejected，数据查询被拒绝，应告知用户并说明原因。\n",
            ask_user_result_line,
            "## 结果类型规则\n",
            f"- 调用 {q}*/{c}* 工具后，返回中含 _hint 字段：必须使用 result_type=query_result，"
            "系统会自动透传完整的 records/pagination/meta/file 结构。\n",
            "- 如需同时返回文字分析+结构化数据：result_type=query_result，answer 填写文字分析，系统会先推文字再推 6001 内容。\n",
            "- 禁止将查询工具返回的 records 序列化后填入 data 字段，会丢失 meta/pagination/file 信息。\n",
            "- CSV 文件：result_type=csv_file。\n",
            "- 纯文字结论：result_type=text。",
        ]
    )
    return "".join(parts)


def _build_exec_en() -> str:

    hint = _get_query_tool_hint_en()
    q, c = _virtual_prefixes()

    return (
        "## Execution rules\n"
        "- Use tools to complete tasks. Call finish_react when done.\n"
        "- Each tool call must include a reason field.\n"
        + (hint if hint else "")
        + "## Compute tool rules\n"
        + f"- For {c}{{object}}, each metrics item must use the key **`agg`** "
        "(e.g. count_distinct), never `func`.\n"
        + "## Query tool return structure\n"
        + f"- {q}*/{c}* return: {{data: {{result_type, records, file: {{file_url}}, meta}}}}.\n"
        "- If file_url or _hint present, data is saved. Do NOT call write_file.\n"
        "## Result type rules\n"
        "- records: result_type=json. file_url or _result: result_type=json_file.\n"
        "- CSV: result_type=csv_file. Text: result_type=text."
    )


def get_execution_prompt(locale: str | None = None) -> str:
    """Return locale-specific execution rules prompt with fallback support.



    Chinese rules are built per call so ``DATACLOUD_DISABLE_ASK_USER_TOOL`` reflects

    the current process environment (after ``load_dotenv``), not import-time env.

    """

    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)

    if resolved_locale == "en_US":
        return _build_exec_en()

    return _build_exec_zh()
