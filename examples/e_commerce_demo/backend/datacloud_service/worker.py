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

# 专门针对 Windows 系统切换事件循环策略以兼容 psycopg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import Any, Optional

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
from datacloud_service.commands import handle_ext_command


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

    def _build_graph(self, prompts_dict: dict | None = None, tools_dict: dict | None = None) -> Any:
        """Instantiate the datacloud-analysis compiled graph with dynamic context."""
        return create_agent(
            model=self.model_name,   # create_agent 内部会自动加 openai: 前缀
            api_key=self.api_key,
            base_url=self.base_url,
            prompts_overwrite=prompts_dict,
            tools=tools_dict,
        )

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
        return [os.environ.get("DATACLOUD_GATEWAY_WORKER_ID","datacloud")]

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

        # 提取 extra_payload 信息（Ask 和 Resume 均携带 agent_id / conf_hash）
        extra_payload = getattr(command, "extra_payload", {}) or {}
        by_agent_id = extra_payload.get("agent_id")
        by_agent_name = extra_payload.get("agent_name")
        ext_params = extra_payload.get("ext_params")
        logger.info(
            "Agent context: ID=%s (type=%s), Name=%s",
            by_agent_id,
            type(by_agent_id).__name__,
            by_agent_name,
        )

        # 获取当前挂载的 Workspace
        from by_framework.worker.sandbox.hook_sandbox import active_workspace  # noqa: PLC0415
        workspace_dir = active_workspace.get()
        logger.info("Active workspace for task: %s", workspace_dir)

        # ② ext_params 短路：仅 AskAgentCommand 路径执行，Resume 不做此检查
        if isinstance(command, AskAgentCommand) and isinstance(ext_params, dict):
            handled, payload = handle_ext_command(
                ext_params=ext_params,
                session_id=context.session_id,
                workspace_dir=workspace_dir,
            )
            if handled:
                if payload is not None:
                    await self._emit_6001(context, payload)
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

        # 版本化缓存：配置变化时自动重建图
        conf_payload = json.dumps(
            {"prompts": prompts_dict, "tool_keys": sorted(tools_dict.keys())},
            ensure_ascii=False,
            sort_keys=True,
        )
        conf_hash = hashlib.sha1(conf_payload.encode("utf-8")).hexdigest()[:12]
        cache_key = f"{by_agent_id}:{conf_hash}" if by_agent_id else f"default:{conf_hash}"

        target_graph = self.graphs.get(cache_key)
        if not target_graph:
            if config_for_this_call:
                target_graph = self._build_graph(
                    prompts_dict=prompts_dict,
                    tools_dict=tools_dict,
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
                "gateway_context": context,   # Bug 6 fix: AgentContext 放 config 而非 state
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
            # Resume 路径：用 Command(resume=...) 续跑，禁止重建 state
            # Bug 2 fix: use `or` so empty string/dict falls through to content
            resume_value = command.reply_data or command.content
            logger.info("ResumeCommand: resume_value type=%s", type(resume_value).__name__)
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
                "plan": [],
                "results": [],
                "intent": "",
                "clarify_needed": False,
                "query_mode": "analysis",
                "target_tool": "",
                "tool_params": {},
            }

        # ⑦ 流式驱动图，处理 GraphInterrupt
        return await self._stream_graph(
            target_graph=target_graph,
            graph_input=graph_input,
            config=config,
            context=context,
            by_agent_id=by_agent_id or "",
            conf_hash=conf_hash,
        )

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
        async for event in target_graph.astream_events(graph_input, config=config, version="v2"):
            await context.check_cancelled()
            kind: str = event["event"]

            if kind == "on_tool_start":
                tool_name: str = event.get("name", "unknown_tool")
                await context.emit_chunk(
                    StreamChunkEvent(content=f"调用工具: {tool_name}"),
                    event_type=EventType.TASK_CREATE.value,
                    content_type=SseReasonMessageType.task_title.value,
                )
            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown_tool")
                await context.emit_chunk(
                    StreamChunkEvent(content=f"工具完成: {tool_name}"),
                    event_type=EventType.STEP_COMPLETE.value,
                    content_type=SseReasonMessageType.task_finished.value,
                )
            # on_chat_model_stream: insight_node 自己通过 context.emit_chunk 推送，worker 不重复转发

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

        if snapshot is not None and snapshot.interrupts:
            # Bug 1 fix: interrupt() 的值在 snapshot.interrupts[0].value，而非 exc.args
            first = snapshot.interrupts[0]
            interrupt_value = first.value
            if isinstance(interrupt_value, dict):
                prompt = interrupt_value.get("prompt", str(interrupt_value))
            else:
                prompt = str(interrupt_value) if interrupt_value else "请补充您的回答"

            checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id", "")
            # Bug 5 fix: 补充 checkpoint_ns（子图场景必填）
            checkpoint_ns = snapshot.config.get("configurable", {}).get("checkpoint_ns", "")

            logger.info(
                "Graph interrupted: session=%s checkpoint_id=%s prompt=%r",
                context.session_id,
                checkpoint_id,
                prompt,
            )
            await context.ask_user(AskUserEvent(
                prompt=prompt,
                metadata={
                    "thread_id": config["configurable"]["thread_id"],
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_ns": checkpoint_ns,
                    "agent_id": by_agent_id,
                    "conf_hash": conf_hash,
                },
            ))
            # 补充结束的标志
            await context.emit_chunk(
                StreamChunkEvent(content="回答完成"),
                event_type=EventType.APP_STREAM_RESPONSE.value,
                content_type=SseMessageType.text.value,
            )
            # 不调用 flush_to_history：对话尚未完成
            return {"status": "waiting"}

        # 正常结束：推送完成通知并写入历史
        await context.emit_chunk(
            StreamChunkEvent(content="回答完成"),
            event_type=EventType.APP_STREAM_RESPONSE.value,
            content_type=SseMessageType.text.value,
        )
        await context.flush_to_history()
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
