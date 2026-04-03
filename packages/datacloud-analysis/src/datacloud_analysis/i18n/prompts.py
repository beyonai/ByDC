"""Provide locale-specific system prompts for DataCloud agent."""

from __future__ import annotations

import os

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


def _disable_ask_user_tool() -> bool:
    """Match ``execution/node.py``: when True, builtin ``ask_user`` is not mounted."""

    return os.environ.get("DATACLOUD_DISABLE_ASK_USER_TOOL", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def get_system_prompt(locale: str | None = None) -> str:
    """Return locale-specific system prompt with fallback support."""
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)
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
        parts.append(
            "- 仅当问题含义不清或工具明确要求追问时，才使用 ask_user（详见下方规则）。\n"
        )
    else:
        parts.append(
            "- 当前未挂载 ask_user 工具：禁止试图调用 ask_user。"
            "若需用户补充信息，请直接调用 finish_react（result_type=text）"
            "在 answer 中用中文写清楚需要用户提供什么。\n"
        )
    parts.extend(
        [
            "- 代码执行前请先使用 write_code 写入文件，再用 execute_code 运行。\n",
            "- 每次工具调用必须填写 reason 字段，说明选择该工具的理由。\n",
        ]
    )
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
        parts.append(
            "- 查询工具成功返回数据后，应直接调用 finish_react，不得再试图追问用户。\n"
        )

    ask_user_result_line = (
        "- 如果 result_type=ask_user，需要向用户追问，使用 ask_user 工具。\n"
        if not no_ask
        else (
            "- 如果 result_type=ask_user 或接口要求追问用户："
            "未挂载追问工具，请调用 finish_react（result_type=text）"
            "并在 answer 中写出要问用户的内容，勿再试图调用 ask_user。\n"
        )
    )
    parts.extend(
        [
            "## 查询工具参数规则\n",
            "- 调用数据查询工具时，query 参数必须是完整的自然语言问题，描述用户真正想查询的内容，例如「查询企业分析表的全部字段」。\n",
            "- 禁止使用 *、%、ALL 等通配符或占位符作为 query 参数。\n",
            "- 如果用户原始问题较短，应结合上下文将其改写为完整、清晰的自然语言查询。\n",
            "## data_query 返回结构规则\n",
            "- data_query 返回结构：{data: {result_type, records, file: {file_url}, meta}}。\n",
            "- 如果返回中包含 file_url 字段或顶层 _hint 字段，说明数据已存入本地文件，禁止再调用 write_file，直接使用该文件路径。\n",
            "- 如果 result_type=rejected，数据查询被拒绝，应告知用户并说明原因。\n",
            ask_user_result_line,
            "## 多步分析工作流\n",
            "- 如需多次查询后再编码分析：\n",
            "  1. 如果查询返回了 file_url，直接用该路径；否则用 write_file 保存 records。\n",
            "  2. 用 write_code 编写分析代码，代码中用 open() 读取 JSON 文件。\n",
            "  3. 代码必须将最终结果赋值给变量 _result，execute_code 会自动保存为同名 .json。\n",
            "  4. 调用 finish_react 使用 result_type=json_file，csv_file_path 填 result_file 路径。\n",
            "## 结果类型规则\n",
            "- 调用 data_query 类工具后，返回中含 _hint 字段：必须使用 result_type=query_result，"
            "系统会自动透传完整的 records/pagination/meta/file 结构。\n",
            "- 如需同时返回文字分析+结构化数据：result_type=query_result，answer 填写文字分析，系统会先推文字再推 6001 内容。\n",
            "- 禁止将 data_query 返回的 records 序列化后填入 data 字段，会丢失 meta/pagination/file 信息。\n",
            "- 代码生成数据（execute_code 保存的 .json）：result_type=json_file，csv_file_path 填 result_file 路径。\n",
            "- CSV 文件：result_type=csv_file。\n",
            "- 纯文字结论：result_type=text。",
        ]
    )
    return "".join(parts)


_EXECUTION_PROMPT_EN_US = (
    "## Execution rules\n"
    "- Use tools to complete tasks. Call finish_react when done.\n"
    "- Each tool call must include a reason field.\n"
    "## data_query rules\n"
    "- Returns {data: {result_type, records, file: {file_url}, meta}}.\n"
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
        return _EXECUTION_PROMPT_EN_US
    return _build_exec_zh()
