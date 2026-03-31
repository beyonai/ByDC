"""DataCloud Gateway Worker.

将 datacloud-analysis LangGraph 接入 by_framework（Gateway）worker 协议：
- 收 AskAgentCommand 消息
- 归一化消息格式，驱动图执行
- 通过 EventType 将 LLM token/工具调用状态实时回传
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping

# 专门针对 Windows 系统切换事件循环策略以兼容 psycopg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Any, Optional, cast

from by_framework import (
    AgentContext,
    AskUserEvent,
    EventType,
    GatewayCommand,
    GatewayWorker,
    ResumeCommand,
    StreamChunkEvent,
)
from by_framework.common.logger import logger
from by_framework.core.extensions import PluginRegistry
from by_framework.core.protocol.commands import AskAgentCommand
from by_framework.core.protocol.content_type import SseMessageType, SseReasonMessageType
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from datacloud_analysis.agent import create_agent
from datacloud_analysis.command_plugins import CommandPluginManager


_CHITCHAT_DIRECT_REPLY = "你好，我在。需要我帮你查询或分析什么数据？"
_CHITCHAT_TOKENS = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "在吗",
    "谢谢",
    "早上好",
    "中午好",
    "下午好",
    "晚上好",
}
_ANALYSIS_HINT_TOKENS = {
    "查",
    "查询",
    "分析",
    "统计",
    "报表",
    "销量",
    "销售",
    "订单",
    "数据",
    "多少",
    "趋势",
    "sql",
    "report",
    "query",
    "analy",
}


_TOOL_DISPLAY = {
    "search_knowledge": ("正在检索业务知识库", "业务知识检索完成"),
    "recall_memory": ("正在回溯相关经验", "相关经验回溯完成"),
    "sbx_run_code": ("正在执行数据分析", "数据分析执行完成"),
    "sbx_read_file": ("正在读取分析文件", "分析文件读取完成"),
    "sbx_write_file": ("正在保存分析结果", "分析结果保存完成"),
    "build_skill": ("正在构建分析技能", "分析技能构建完成"),
    "render_report": ("正在生成分析报告", "分析报告生成完成"),
    "choose_capability": ("正在规划下一步操作", ""),
}


def _tool_display(tool_name: str) -> tuple[str, str]:
    """Return (start_desc, end_desc) pair for a given tool name."""

    return _TOOL_DISPLAY.get(tool_name, ("正在处理...", "处理完成"))


def _extract_tool_detail(tool_name: str, tool_input: Any) -> str:
    """Extract user-meaningful detail from tool parameters."""

    if not isinstance(tool_input, dict):
        return ""
    if tool_name in {"sbx_read_file", "sbx_write_file"}:
        path_value = tool_input.get("file_path") or tool_input.get("path") or ""
        if path_value:
            return os.path.basename(str(path_value))
        return ""
    if tool_name in {"search_knowledge", "recall_memory"}:
        query_value = str(tool_input.get("query") or "").strip()
        return query_value[:30]
    return ""


def _compiled_graph_has_checkpointer(graph: Any) -> bool:
    """Return True if LangGraph was compiled with a usable checkpointer.

    ``Pregel.aget_state`` raises ``ValueError('No checkpointer set')`` when this is false.
    """

    cp = getattr(graph, "checkpointer", None)
    if cp is True:
        return True
    return isinstance(cp, BaseCheckpointSaver)


_no_checkpointer_logged: bool = False


class DataCloudWorker(GatewayWorker):
    """Worker that drives the datacloud-analysis graph inside the Gateway worker protocol.

    启动时通过 run_worker(**worker_kwargs) 将以下参数透传至 __init__：
        model_name  — LLM 模型名（读自 .env DATACLOUD_LLM_REASONING_MODEL）
        api_key     — OpenAI-compatible API key（读自 .env OPENAI_API_KEY）
        base_url    — OpenAI-compatible base URL（读自 .env OPENAI_BASE_URL）
    """

    # 图实例缓存的最大条目数；超过时淘汰最久未使用的条目
    _GRAPH_CACHE_MAX: int = 32
    _RESUME_RESULT_CACHE_MAX: int = 256

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        plugin_registry: Optional[PluginRegistry] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(plugin_registry=plugin_registry, *args, **kwargs)
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        # 使用 OrderedDict 实现 LRU 缓存，防止长期运行内存无限增长
        self.graphs: OrderedDict = OrderedDict()
        self._resume_result_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._resume_inflight: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.command_plugin_manager = CommandPluginManager.from_defaults()

    def _build_resume_dedup_key(
        self,
        *,
        session_id: str,
        checkpoint_id: str,
        checkpoint_ns: str,
        resume_value: Any,
    ) -> str:
        try:
            resume_payload = json.dumps(resume_value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            resume_payload = repr(resume_value)
        raw = json.dumps(
            {
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": checkpoint_ns,
                "resume_payload": resume_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_resume_result(self, key: str, result: dict[str, Any]) -> None:
        self._resume_result_cache[key] = dict(result)
        self._resume_result_cache.move_to_end(key)
        while len(self._resume_result_cache) > self._RESUME_RESULT_CACHE_MAX:
            self._resume_result_cache.popitem(last=False)

    @staticmethod
    def _consume_future_exception(fut: asyncio.Future[dict[str, Any]]) -> None:
        if fut.cancelled():
            return
        try:
            fut.exception()
        except Exception:
            return

    def _build_graph(self, prompts_dict: dict | None = None, tools_dict: dict | None = None) -> Any:
        """Instantiate the datacloud-analysis compiled graph with dynamic context."""
        return create_agent(
            model=self.model_name,  # create_agent 内部会自动加 openai: 前缀
            api_key=self.api_key,
            base_url=self.base_url,
            prompts_overwrite=prompts_dict,
            tools=tools_dict,
        )

    @staticmethod
    def _wrap_skill_callable(
        skill_name: str,
        run_fn: Callable[..., Any],
        skill_meta: Mapping[str, Any] | None = None,
    ) -> Callable[..., Awaitable[Any]]:
        async def _skill_tool(**params: Any) -> Any:
            maybe = run_fn(**params)
            if hasattr(maybe, "__await__"):
                return await maybe
            return maybe

        metadata = dict(skill_meta or {})
        allowlist_tags = [str(tag).strip() for tag in metadata.get("allowlist_tags") or [] if str(tag).strip()]
        blocklist_tags = [str(tag).strip() for tag in metadata.get("blocklist_tags") or [] if str(tag).strip()]
        risk_level = str(metadata.get("risk_level") or "medium").strip().lower() or "medium"

        _skill_tool.__name__ = f"skill_{skill_name}"
        _skill_tool.__doc__ = f"Skill capability: {skill_name}"
        setattr(_skill_tool, "_is_skill_capability", True)
        setattr(_skill_tool, "_skill_name", skill_name)
        setattr(_skill_tool, "_skill_meta", metadata)
        setattr(_skill_tool, "_skill_risk_level", risk_level)
        setattr(_skill_tool, "_skill_allowlist_tags", allowlist_tags)
        setattr(_skill_tool, "_skill_blocklist_tags", blocklist_tags)
        return _skill_tool

    def _load_skill_capabilities(
        self,
        *,
        user_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        try:
            from datacloud_analysis.workspace.paths import build_task_paths  # noqa: PLC0415
            from datacloud_analysis.workspace.skills_loader import SkillLoader  # noqa: PLC0415
        except ImportError as exc:
            logger.warning("Skill capability loader unavailable: %s", exc)
            return {}

        try:
            task_paths = build_task_paths(user_id=user_id, task_id=task_id)
            loader = SkillLoader(task_paths)
            registry = loader.load_all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load skill capabilities user=%s task=%s error=%s", user_id, task_id, exc)
            return {}

        skills: dict[str, Any] = {}
        source_counts: dict[str, int] = {}
        for name, entry in registry.items():
            run_fn = entry.get("run")
            if not callable(run_fn):
                continue
            skill_name = str(name).strip()
            if not skill_name:
                continue
            skills[skill_name] = self._wrap_skill_callable(
                skill_name,
                run_fn,
                cast(Mapping[str, Any] | None, entry.get("meta")),
            )
            source = str(entry.get("source", "unknown"))
            source_counts[source] = source_counts.get(source, 0) + 1
        if skills:
            logger.info(
                "Loaded skill capabilities: count=%d names=%s sources=%s",
                len(skills),
                sorted(skills.keys()),
                source_counts,
            )
        return skills

    async def start_heartbeat(self) -> None:
        """Worker 启动后拦截."""
        await super().start_heartbeat()

        init_plugin = self.plugin_registry.get_plugin("datacloud_init_agent_conf")
        loaded_agent_ids = getattr(init_plugin, "loaded_agent_ids", []) if init_plugin else []
        if not loaded_agent_ids:
            raise RuntimeError("启动失败：未加载到任何数字员工配置")
        logger.info(
            "Init plugin loaded digital employees: count=%d ids=%s",
            len(loaded_agent_ids),
            loaded_agent_ids,
        )

        # 初始化 SDK 环境 (PG 数据库建表, Checkpoint, Memory 等)
        from datacloud_analysis import bootstrap

        await bootstrap.setup()

        logger.info("DataCloudWorker: SDK framework bootstrapped.")

    def get_capabilities(self) -> list[str]:
        """向 gateway 注册本 worker 的能力标签。"""
        return [os.environ.get("DATACLOUD_GATEWAY_WORKER_ID", "datacloud")]

    async def _emit_6001(self, context: AgentContext, payload: dict[str, Any]) -> None:
        """Emit one structured data-table JSON chunk (content_type=6001)."""
        data_table_type = getattr(SseMessageType, "data_table_json", None)
        content_type = data_table_type.value if data_table_type is not None else "6001"
        await context.emit_chunk(
            StreamChunkEvent(content=json.dumps(payload, ensure_ascii=False)),
            event_type=EventType.ANSWER_DELTA.value,
            content_type=content_type,
        )

    # ------------------------------------------------------------------
    # 核心消息处理
    # ------------------------------------------------------------------

    async def process_command(self, command: GatewayCommand, context: AgentContext) -> dict:
        """Receive a command, run the graph, and stream events back to the caller.

        Handles two command types:
        - AskAgentCommand: fresh conversation turn, builds initial graph state.
        - ResumeCommand:   resumes a suspended graph via Command(resume=...).

        Returns:
            {"status": "done"}    — normal completion, flush_to_history called.
            {"status": "waiting"} — graph interrupted, ask_user emitted, no flush.
        """
        logger.info(
            "DataCloudWorker.process_command: session=%s command=%s",
            context.session_id,
            type(command).__name__,
        )

        # ① 同步 Worker 构造参数 → os.environ，确保图内节点 os.getenv 拿到正确值
        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
        if self.base_url:
            os.environ["OPENAI_BASE_URL"] = self.base_url
        if self.model_name:
            os.environ["DATACLOUD_LLM_REASONING_MODEL"] = self.model_name

        # 提取 payload / header metadata 信息（Resume 可能只在 metadata 里带 agent_id/conf_hash）
        extra_payload = getattr(command, "extra_payload", {}) or {}
        header_metadata = getattr(getattr(command, "header", None), "metadata", None) or {}
        by_agent_id = extra_payload.get("agent_id") or header_metadata.get("agent_id")
        by_agent_name = extra_payload.get("agent_name") or header_metadata.get("agent_name")
        ext_params = extra_payload.get("ext_params")
        logger.info(
            "Agent context: ID=%s (type=%s), Name=%s",
            by_agent_id,
            type(by_agent_id).__name__,
            by_agent_name,
        )

        resume_cache_key: str | None = None
        if isinstance(command, ResumeCommand):
            resume_value_probe = command.reply_data if command.reply_data is not None else command.content
            checkpoint_id_probe = str(header_metadata.get("checkpoint_id") or "")
            checkpoint_ns_probe = str(header_metadata.get("checkpoint_ns") or "")
            resume_cache_key = self._build_resume_dedup_key(
                session_id=context.session_id,
                checkpoint_id=checkpoint_id_probe,
                checkpoint_ns=checkpoint_ns_probe,
                resume_value=resume_value_probe,
            )
            cached = self._resume_result_cache.get(resume_cache_key)
            if cached is not None:
                logger.info(
                    "ResumeCommand idempotent hit: session=%s checkpoint_id=%s checkpoint_ns=%s",
                    context.session_id,
                    checkpoint_id_probe,
                    checkpoint_ns_probe,
                )
                self._resume_result_cache.move_to_end(resume_cache_key)
                return dict(cached)

        # 获取当前挂载的 Workspace
        from by_framework.worker.sandbox.hook_sandbox import active_workspace  # noqa: PLC0415

        workspace_dir = active_workspace.get()
        logger.info("Active workspace for task: %s", workspace_dir)

        # ② ext_params 短路：仅 AskAgentCommand 路径执行，Resume 不做此检查
        if isinstance(command, AskAgentCommand) and isinstance(ext_params, dict):
            handled, payload = await self.command_plugin_manager.handle_ext_command(
                ext_params=ext_params,
                session_id=context.session_id,
                workspace_dir=workspace_dir,
                gateway_context=context,
            )
            if handled:
                if payload is not None:
                    await self._emit_6001(context, payload)
                if not bool(ext_params.get("silent")):
                    await context.emit_chunk(
                        StreamChunkEvent(content="回答完成"),
                        event_type=EventType.APP_STREAM_RESPONSE.value,
                        content_type=SseMessageType.text.value,
                    )
                    await context.flush_to_history()
                return {"status": "done"}

        # Ask 路径轻量闲聊短路：命中后直接回复，不进入 LangGraph。
        if isinstance(command, AskAgentCommand):
            user_text = _latest_user_text_from_content(command.content)
            if _is_light_chitchat(user_text):
                await context.emit_chunk(
                    StreamChunkEvent(
                        content=_CHITCHAT_DIRECT_REPLY,
                        metadata={"graph_nodes_executed": 0},
                    ),
                    event_type=EventType.ANSWER_DELTA.value,
                    content_type=SseMessageType.text.value,
                )
                await context.emit_chunk(
                    StreamChunkEvent(content="回答完成"),
                    event_type=EventType.APP_STREAM_RESPONSE.value,
                    content_type=SseMessageType.text.value,
                )
                await context.flush_to_history()
                return {"status": "done"}

        # ③ 查找 Agent 配置，构建图缓存键
        agent_configs = context.list_agent_configs()
        config_for_this_call = next(
            (cfg for cfg in agent_configs if str(cfg.agent_id) == str(by_agent_id)),
            None,
        )
        logger.info(
            "Agent config match result: by_agent_id=%s matched=%s",
            by_agent_id,
            bool(config_for_this_call),
        )
        tools_dict = getattr(config_for_this_call, "tools", None) or {}
        prompts_dict = getattr(config_for_this_call, "prompts", None) or {}
        logger.info(
            "Agent config payload: agent_id=%s prompt_keys=%s tool_keys=%s",
            by_agent_id,
            sorted(str(key) for key in prompts_dict.keys()),
            sorted(str(key) for key in tools_dict.keys()),
        )
        user_id = str(getattr(context, "user_id", "") or "anonymous")
        skill_tools = self._load_skill_capabilities(user_id=user_id, task_id=context.session_id)
        merged_tools = dict(tools_dict)
        if skill_tools:
            for skill_name, skill_tool in skill_tools.items():
                if skill_name in merged_tools:
                    alias = f"skill.{skill_name}"
                    merged_tools[alias] = skill_tool
                    logger.info(
                        "Skill name conflict with tool: name=%s alias=%s",
                        skill_name,
                        alias,
                    )
                else:
                    merged_tools[skill_name] = skill_tool
        logger.info(
            "Agent runtime merged tools: agent_id=%s merged_tool_keys=%s skill_tool_count=%d",
            by_agent_id,
            sorted(str(key) for key in merged_tools.keys()),
            len(skill_tools),
        )

        # 版本化缓存：配置变化时自动重建图
        conf_payload = json.dumps(
            {"prompts": prompts_dict, "tool_keys": sorted(merged_tools.keys())},
            ensure_ascii=False,
            sort_keys=True,
        )
        computed_conf_hash = hashlib.sha1(conf_payload.encode("utf-8")).hexdigest()[:12]
        resume_conf_hash = ""
        if isinstance(command, ResumeCommand):
            resume_conf_hash = str(header_metadata.get("conf_hash") or "").strip()
            if resume_conf_hash and resume_conf_hash != computed_conf_hash:
                logger.warning(
                    "ResumeCommand conf_hash mismatch: metadata=%s computed=%s; "
                    "using metadata hash for cache affinity",
                    resume_conf_hash,
                    computed_conf_hash,
                )
        conf_hash = resume_conf_hash or computed_conf_hash
        cache_key = f"{by_agent_id}:{conf_hash}" if by_agent_id else f"default:{conf_hash}"

        target_graph = self.graphs.get(cache_key)
        if not target_graph:
            if config_for_this_call:
                target_graph = self._build_graph(
                    prompts_dict=prompts_dict,
                    tools_dict=merged_tools,
                )
            else:
                logger.warning("AgentConfig for %s not found, fallback to defaults.", by_agent_id)
                target_graph = self._build_graph()
            self.graphs[cache_key] = target_graph
            while len(self.graphs) > self._GRAPH_CACHE_MAX:
                evicted_key, _ = self.graphs.popitem(last=False)
                logger.info("Graph cache evicted: key=%s", evicted_key)
        else:
            self.graphs.move_to_end(cache_key)

        # ④ 设置 LangGraph config（thread_id 用于 checkpoint，gateway_context 不进 state 避免序列化失败）
        config = {
            "configurable": {
                "thread_id": context.session_id,
                "gateway_context": context,  # Bug 6 fix: AgentContext 放 config 而非 state
            }
        }

        # ⑤ 发送"开始推理"通知
        await context.emit_chunk(
            StreamChunkEvent(content="思考中..."),
            event_type=EventType.REASONING_LOG_START.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        await context.emit_chunk(
            StreamChunkEvent(content="已接收到用户消息，开始处理"),
            event_type=EventType.REASONING_LOG_START.value,
            content_type=SseReasonMessageType.think_text.value,
        )

        # ⑥ 根据命令类型构建图输入
        if isinstance(command, ResumeCommand):
            try:
                resume_payload_json = json.dumps(
                    command.to_dict(),
                    ensure_ascii=False,
                    default=str,
                )
            except Exception:
                resume_payload_json = repr(command)
            logger.info(
                "ResumeCommand received session=%s trace_id=%s payload=%s",
                context.session_id,
                getattr(command.header, "trace_id", ""),
                resume_payload_json,
            )
            # Resume 路径：用 Command(resume=...) 续跑，禁止重建 state
            # reply_data 允许空字符串/空对象，只有 None 时才回落到 content
            resume_value = command.reply_data if command.reply_data is not None else command.content
            if isinstance(resume_value, str):
                resume_preview = resume_value[:500]
            else:
                try:
                    resume_preview = json.dumps(resume_value, ensure_ascii=False, default=str)[:500]
                except (TypeError, ValueError):
                    resume_preview = repr(resume_value)[:500]
            logger.info(
                "ResumeCommand: resume_value type=%s preview=%s",
                type(resume_value).__name__,
                resume_preview,
            )
            graph_input: Any = Command(resume=resume_value)
        else:
            # Ask 路径：归一化消息，构建完整初始 state
            input_messages = _normalize_messages(command.content)
            # prompts_overwrite / dynamic_tools 不得放入 checkpoint 状态：工具对象内含
            # Python callable，LangGraph PG serde 会报「not msgpack serializable: function」。
            # 二者由 build_analysis_graph(..., prompts_overwrite=, tools=) 闭包注入各节点。
            graph_input = {
                "messages": input_messages,
                "agent_id": by_agent_id,
                "agent_name": by_agent_name,
                "workspace_dir": workspace_dir,
                "user_query": "",
                "enriched_query": "",
                "plan": [],
                "todos": [],
                "todo_md": "",
                "todo_md_path": "",
                "results": [],
                "execution_status": "",
                "todo_active_id": "",
                "todo_tool_plan": [],
                "active_tools": [],
                "execution_trace": [],
                "invocation_dedup": [],
                "final_answer": "",
                "artifact_refs": [],
                "execution_summary": None,
                "execution_summary_persistence": None,
                "resume_context": {},
                "intent": "",
                "clarify_needed": False,
                "query_mode": "analysis",
                "chitchat_reply": None,
                "target_tool": "",
                "tool_params": {},
                "term_hints": [],
                "knowledge_snippets": [],
                "knowledge_payload": {},
                "concept_terms": [],
                "confirmed_terms": [],
                "ambiguous_terms": [],
                "session_alias_map": {},
            }

        # Resume：把网关 header.metadata 里的 checkpoint 写入 LangGraph configurable。
        # 若不传 checkpoint_id，PG checkpointer 会按 thread 取「最新」快照；该快照往往已越过
        # interrupt 点，Command(resume=...) 无法接到挂起任务，表现为 astream_events 极少、秒结束。
        if isinstance(command, ResumeCommand):
            md = header_metadata
            ckpt_id = md.get("checkpoint_id")
            if ckpt_id:
                config["configurable"]["checkpoint_id"] = str(ckpt_id)
                config["configurable"]["checkpoint_ns"] = str(md.get("checkpoint_ns", ""))
            logger.info(
                "ResumeCommand: langgraph checkpoint_id=%s checkpoint_ns=%r (from header.metadata)",
                config["configurable"].get("checkpoint_id", ""),
                config["configurable"].get("checkpoint_ns", ""),
            )

        # ⑦ 流式驱动图，处理 GraphInterrupt
        resume_inflight_owner = False
        resume_inflight_future: asyncio.Future[dict[str, Any]] | None = None
        if isinstance(command, ResumeCommand) and resume_cache_key:
            inflight = self._resume_inflight.get(resume_cache_key)
            if inflight is not None:
                logger.info(
                    "ResumeCommand inflight hit: session=%s checkpoint_id=%s checkpoint_ns=%s",
                    context.session_id,
                    str(header_metadata.get("checkpoint_id") or ""),
                    str(header_metadata.get("checkpoint_ns") or ""),
                )
                inflight_result = await asyncio.shield(inflight)
                return dict(inflight_result)
            resume_inflight_owner = True
            resume_inflight_future = asyncio.get_running_loop().create_future()
            resume_inflight_future.add_done_callback(self._consume_future_exception)
            self._resume_inflight[resume_cache_key] = resume_inflight_future

        try:
            logger.info(
                "⑦ _stream_graph invoke session=%s input_is_command_resume=%s",
                context.session_id,
                isinstance(graph_input, Command),
            )
            stream_result = await self._stream_graph(
                target_graph=target_graph,
                graph_input=graph_input,
                config=config,
                context=context,
                by_agent_id=by_agent_id or "",
                conf_hash=conf_hash,
            )
            if isinstance(command, ResumeCommand) and resume_cache_key:
                self._cache_resume_result(resume_cache_key, stream_result)
            if (
                resume_inflight_owner
                and resume_inflight_future is not None
                and not resume_inflight_future.done()
            ):
                resume_inflight_future.set_result(dict(stream_result))
            return stream_result
        except Exception as exc:
            if (
                resume_inflight_owner
                and resume_inflight_future is not None
                and not resume_inflight_future.done()
            ):
                resume_inflight_future.set_exception(exc)
            raise
        finally:
            if resume_inflight_owner and resume_cache_key:
                self._resume_inflight.pop(resume_cache_key, None)

    async def _stream_graph(
        self,
        *,
        target_graph: Any,
        graph_input: Any,
        config: dict,
        context: AgentContext,
        by_agent_id: str,
        conf_hash: str,
    ) -> dict:
        """Drive the graph via astream_events, then check for interrupt via aget_state.

        LangGraph's root-graph suppresses GraphInterrupt internally — it never propagates
        through astream_events.  The correct detection pattern is to call aget_state()
        after the stream ends and inspect snapshot.interrupts.

        Returns:
            {"status": "done"}    — normal completion.
            {"status": "waiting"} — graph interrupted, ask_user already emitted.
        """
        is_agent_delegate = False
        stream_event_count = 0
        logger.info(
            "_stream_graph: astream_events begin session=%s conf_hash=%s",
            context.session_id,
            conf_hash,
        )
        async for event in target_graph.astream_events(graph_input, config=config, version="v2"):
            stream_event_count += 1
            await context.check_cancelled()
            kind: str = event["event"]

            if kind == "on_chain_end" and event.get("name") == "agent_delegate":
                is_agent_delegate = True
            elif kind == "on_tool_start":
                tool_name = str(event.get("name") or "unknown_tool")
                tool_input = (event.get("data") or {}).get("input", {})
                start_desc, _ = _tool_display(tool_name)
                detail = _extract_tool_detail(tool_name, tool_input)
                display_text = f"{start_desc}：{detail}" if detail else start_desc
                await context.emit_chunk(
                    StreamChunkEvent(content=display_text),
                    event_type=EventType.TASK_CREATE.value,
                    content_type=SseReasonMessageType.task_title.value,
                )
            elif kind == "on_tool_end":
                tool_name = str(event.get("name") or "unknown_tool")
                _, end_desc = _tool_display(tool_name)
                if end_desc:
                    await context.emit_chunk(
                        StreamChunkEvent(content=end_desc),
                        event_type=EventType.STEP_COMPLETE.value,
                        content_type=SseReasonMessageType.task_finished.value,
                    )
            # on_chat_model_stream: insight_node 自己通过 context.emit_chunk 推送，worker 不重复转发

        logger.info(
            "_stream_graph: astream_events end session=%s event_count=%d",
            context.session_id,
            stream_event_count,
        )

        # GraphInterrupt 被 root 抑制时，流结束后用 aget_state 看 snapshot.interrupts。
        # 若 create_agent 在未 bootstrap 时退化为无 checkpointer 编译，aget_state 会抛
        # ValueError("No checkpointer set") — 必须先判断。
        if _compiled_graph_has_checkpointer(target_graph):
            snapshot = await target_graph.aget_state(config)
        else:
            global _no_checkpointer_logged
            if not _no_checkpointer_logged:
                logger.warning(
                    "Graph has no checkpointer: aget_state skipped, HITL/resume disabled. "
                    "Ensure bootstrap.setup() finished before the first create_agent(), "
                    "or clear graph cache if bootstrap order was wrong."
                )
                _no_checkpointer_logged = True
            snapshot = None

        ckpt_after = (
            snapshot.config.get("configurable", {}).get("checkpoint_id", "")
            if snapshot is not None
            else ""
        )
        logger.info(
            "_stream_graph: after aget_state session=%s snapshot_present=%s "
            "has_interrupts=%s checkpoint_id=%s",
            context.session_id,
            snapshot is not None,
            bool(snapshot.interrupts) if snapshot is not None else False,
            ckpt_after,
        )

        if snapshot is not None and snapshot.interrupts:
            # Bug 1 fix: interrupt() 的值在 snapshot.interrupts[0].value，而非 exc.args
            first = snapshot.interrupts[0]
            interrupt_value = first.value
            interrupt_reason = "unknown_interrupt"
            if isinstance(interrupt_value, dict):
                prompt = interrupt_value.get("prompt", str(interrupt_value))
                interrupt_reason = str(
                    interrupt_value.get("reason_code")
                    or interrupt_value.get("interrupt_reason")
                    or "interrupt"
                )
            else:
                prompt = str(interrupt_value) if interrupt_value else "请补充您的回答"
                if prompt:
                    interrupt_reason = "prompt_interrupt"

            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
            # Bug 5 fix: 补充 checkpoint_ns（子图场景必填）
            checkpoint_ns = snapshot.config.get("configurable", {}).get("checkpoint_ns", "")
            snapshot_values = snapshot.values if isinstance(snapshot.values, dict) else {}
            todo_active_id = str(snapshot_values.get("todo_active_id") or "")
            active_tools = snapshot_values.get("active_tools")
            pending_capability = ""
            if isinstance(active_tools, list) and active_tools:
                pending_capability = str(active_tools[0] or "")
            if not pending_capability:
                pending_capability = str(snapshot_values.get("target_tool") or "")

            logger.info(
                "Graph interrupted: session=%s checkpoint_id=%s prompt=%r",
                context.session_id,
                checkpoint_id,
                prompt,
            )
            await context.ask_user(
                AskUserEvent(
                    prompt=prompt,
                    metadata={
                        "thread_id": config["configurable"]["thread_id"],
                        "checkpoint_id": checkpoint_id,
                        "checkpoint_ns": checkpoint_ns,
                        "agent_id": by_agent_id,
                        "conf_hash": conf_hash,
                        "todo_active_id": todo_active_id,
                        "react_step_id": todo_active_id,
                        "pending_capability": pending_capability,
                        "interrupt_reason": interrupt_reason,
                    },
                )
            )
            # 补充结束的标志
            await context.emit_chunk(
                StreamChunkEvent(
                    content="回答完成",
                    metadata={"relatedResources": ["推荐问题11"]},
                ),
                event_type=EventType.APP_STREAM_RESPONSE.value,
                content_type=SseMessageType.text.value,
            )
            # 不调用 flush_to_history：对话尚未完成
            logger.info(
                "_stream_graph: return session=%s status=waiting",
                context.session_id,
            )
            return {"status": "waiting"}

        # 正常结束：推送完成通知并写入历史
        # ⑥ 回答结束通知（agent_delegate 路径已由子Agent自行结束，无需重复通知）
        if not is_agent_delegate:
            await context.emit_chunk(
                StreamChunkEvent(
                    content="回答完成",
                    metadata={"relatedResources": ["推荐问题11"]},
                ),
                event_type=EventType.APP_STREAM_RESPONSE.value,
                content_type=SseMessageType.text.value,
            )

        await context.flush_to_history()
        logger.info(
            "_stream_graph: return session=%s status=done (flush_to_history ok)",
            context.session_id,
        )
        return {"status": "done"}


# ------------------------------------------------------------------
# 私有工具函数
# ------------------------------------------------------------------


def _normalize_messages(
    content: Any,
) -> list[HumanMessage | AIMessage | SystemMessage]:
    """Convert gateway command content to a list of LangChain BaseMessage.

    Supports:
        - str → single HumanMessage
        - list[dict] with 'role'/'content' keys → typed messages
        - list[str] → list of HumanMessage
    """
    if isinstance(content, str):
        return [HumanMessage(content=content)]

    if not isinstance(content, list):
        return [HumanMessage(content=str(content))]

    messages: list[HumanMessage | AIMessage | SystemMessage] = []
    for item in content:
        if isinstance(item, dict) and "role" in item:
            role = item["role"]
            text = item.get("content", "")
            if role == "assistant":
                messages.append(AIMessage(content=text))
            elif role == "system":
                messages.append(SystemMessage(content=text))
            else:
                messages.append(HumanMessage(content=text))
        else:
            messages.append(HumanMessage(content=str(item)))

    return messages


def _latest_user_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list) or not content:
        return str(content).strip() if content is not None else ""
    last = content[-1]
    if isinstance(last, dict):
        raw = last.get("content", "")
        return raw.strip() if isinstance(raw, str) else str(raw).strip()
    return str(last).strip()


def _is_light_chitchat(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(token in normalized for token in _ANALYSIS_HINT_TOKENS):
        return False
    if normalized in _CHITCHAT_TOKENS:
        return True
    # Keep heuristic narrow to avoid hijacking real requests.
    return len(normalized) <= 10 and any(token in normalized for token in _CHITCHAT_TOKENS)
