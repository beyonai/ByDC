"""DataCloud deep agent — core graph factory.

Persistence (checkpointing) is handled externally:
- langgraph dev: injected by the platform via ``langgraph.json`` / ``checkpointer.py``
  which references ``datacloud_analysis.session.pg_opengauss.get_checkpointer``.
- Standalone SDK: call ``create_agent()`` then compile with your own checkpointer,
  or use ``datacloud_analysis.session.pg_opengauss.make_opengauss_saver`` directly.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from datacloud_analysis.i18n import get_supported_locales
from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_DIAG_QUESTION_KEYS = (
    "user_message",
    "latest_user_text",
    "question",
    "input",
    "task_prompt",
)


def _truncate_text(text: str, max_len: int) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


def _extract_question_context_for_log(
    *,
    user_message: str | None,
    prompts_overwrite: dict[str, Any] | None,
    system_prompt: str | None,
) -> str:
    """Best-effort 本轮/配置侧「问题」摘要，供核查日志使用。"""

    if user_message and str(user_message).strip():
        return _truncate_text(str(user_message), 800)
    po = prompts_overwrite or {}
    for key in _DIAG_QUESTION_KEYS:
        val = po.get(key)
        if isinstance(val, str) and val.strip():
            return _truncate_text(val, 800)
    if system_prompt and str(system_prompt).strip():
        return _truncate_text(str(system_prompt), 400)
    return (
        "(未提供 user_message；prompts_overwrite 中亦无常见问题字段。"
        "create_agent 多在建图时调用，若需对齐某轮提问请在调用处传入 user_message=...)"
    )


def _format_tools_for_diag(tool_map: dict[str, Any] | None) -> str:
    """将合并后的工具表格式化为多行字符串，便于日志检索。"""

    if not tool_map:
        return "  (无工具)"
    rows: list[str] = []
    for name in sorted(tool_map.keys()):
        obj = tool_map[name]
        kind = type(obj).__name__
        desc = ""
        for attr in ("description", "description_text"):
            raw = getattr(obj, attr, None)
            if isinstance(raw, str) and raw.strip():
                desc = _truncate_text(raw, 140)
                break
        rows.append(f"  - {name} [{kind}] {desc}")
    return "\n".join(rows)


def _resolve_agent_id_for_log(
    *,
    agent_id: str | None,
    prompts_overwrite: dict[str, Any] | None,
) -> str:
    """解析日志用的 agent 标识：显式参数优先，其次 prompts_overwrite。"""

    if agent_id is not None and str(agent_id).strip():
        return str(agent_id).strip()
    po = prompts_overwrite or {}
    for key in ("agent_id", "agentId", "resourceId"):
        val = po.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return "(未提供 agent_id)"


def _log_create_agent_diagnostics(
    *,
    agent_id_display: str,
    question_context: str,
    merged_tools: dict[str, Any] | None,
    mounted_objects: list[str] | None,
) -> None:
    """打印建图时的「agent_id + 问题上下文 + 工具清单」，便于线上对照核查。"""

    tool_block = _format_tools_for_diag(merged_tools)
    logger.info(
        "[create_agent diagnostics] ----------\n"
        "agent_id=%s\n"
        "问题/提示上下文:\n%s\n"
        "mounted_objects=%s\n"
        "合并后工具数=%d，清单:\n%s\n"
        "[create_agent diagnostics] ----------",
        agent_id_display,
        question_context,
        mounted_objects,
        len(merged_tools or {}),
        tool_block,
    )


def create_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str | None = None,
    system_prompt: str | None = None,
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    mounted_objects: list[str] | None = None,
    loader: Any | None = None,
    skip_action_families: frozenset[str] = frozenset(),
    user_message: str | None = None,
    agent_id: str | None = None,
    knowledge_enhancer: Callable[..., Any] | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui.

    Args:
        tools: 调用方预构建的工具字典，key 为工具名，value 为可调用对象或 BaseTool。
        mounted_objects: OBJECT / VIEW / ONTOLOGY 编码列表。若提供，则通过
            ``OntologyToolLoader`` 从本体定义自动生成 query_{code} /
            compute_{code} / action 工具，再与 ``tools`` 合并（``tools``
            中同名工具优先，即调用方可覆盖自动生成的工具）。
        loader: ``datacloud_data_sdk.OntologyLoader`` 实例。``mounted_objects``
            非空时必须提供；未提供则跳过本体工具生成并记录 debug 日志。
        user_message: 可选。传入时写入核查日志的「当前提问」；否则从
            ``prompts_overwrite`` 的 ``user_message`` / ``task_prompt`` 等键推断。
        agent_id: 可选。写入核查日志；未传时尝试 ``prompts_overwrite`` 中的
            ``agent_id`` / ``agentId`` / ``resourceId``。
        knowledge_enhancer: 可选。知识增强函数，签名为
            ``(query: str) -> ClarificationResult``（同步或异步均可）。
            传入后，每次 ``intend_node`` 调用时会先调用此函数，将知识摘要写入
            ``knowledge_snippets``、将完整结果写入 ``knowledge_payload``，
            供后续 execution_node 和 query_clarification_plugin 使用（§6.4）。
            典型用法：在调用方用 ``asyncio.to_thread`` 包装同步函数后传入。
    """

    # 语言和环境的日志预警可以保留，这里为了兼容现有 SDK 初始化
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    supported = get_supported_locales()
    if resolved_locale not in supported:
        logger.warning(
            "create_agent: locale=%r is not supported (supported: %s). Falling back to zh_CN.",
            resolved_locale,
            supported,
        )
        resolved_locale = "zh_CN"

    # --- 本体工具生成 ---
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader  # noqa: PLC0415

    ontology_tools = OntologyToolLoader(
        mounted_objects=mounted_objects,
        loader=loader,
        skip_action_families=skip_action_families,
    ).load()

    # 合并工具：本体工具为基础，caller 传入的 tools 优先覆盖同名工具
    merged_tools: dict[str, Any] | None = {**ontology_tools, **(tools or {})} or None

    question_ctx = _extract_question_context_for_log(
        user_message=user_message,
        prompts_overwrite=prompts_overwrite,
        system_prompt=system_prompt,
    )
    agent_id_display = _resolve_agent_id_for_log(
        agent_id=agent_id,
        prompts_overwrite=prompts_overwrite,
    )
    _log_create_agent_diagnostics(
        agent_id_display=agent_id_display,
        question_context=question_ctx,
        merged_tools=merged_tools,
        mounted_objects=mounted_objects,
    )

    logger.info("create_agent: locale=%s (Custom StateGraph)", resolved_locale)
    logger.info(
        "create_agent: tools summary — "
        "ontology=%d extra=%d merged=%d mounted_objects=%s prompts_overwrite_keys=%s",
        len(ontology_tools),
        len(tools or {}),
        len(merged_tools or {}),
        mounted_objects,
        sorted((prompts_overwrite or {}).keys()),
    )

    graph = build_analysis_graph(
        prompts_overwrite=prompts_overwrite,
        tools=merged_tools,
        knowledge_enhancer=knowledge_enhancer,
    )

    # Inject checkpointer if bootstrap.setup() has already been called;
    # fall back to compiling without checkpointing in standalone / test mode.
    try:
        from datacloud_analysis.session.checkpointer import get_checkpointer  # noqa: PLC0415

        compiled = graph.compile(checkpointer=get_checkpointer())
        logger.info("create_agent: compiled with PG checkpointer")
    except RuntimeError:
        compiled = graph.compile()
        logger.warning(
            "create_agent: checkpointer not initialized — compiling without checkpointing. "
            "Call `await bootstrap.setup()` before create_agent() to enable interrupt/resume."
        )

    try:
        nodes = list(compiled.get_graph().nodes.keys())
        logger.info("[dbg] compiled graph nodes: %s", nodes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dbg] get_graph failed: %s", exc)

    return compiled
