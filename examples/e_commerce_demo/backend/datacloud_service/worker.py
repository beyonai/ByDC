"""DataCloud Gateway Worker.

将 datacloud-analysis LangGraph 接入 gateway_sdk worker 协议：
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

from gateway_sdk import (
    AgentContext,
    EventType,
    GatewayWorker,
    StreamChunkEvent,
)
from gateway_sdk.common.logger import logger
from gateway_sdk.core.extensions import PluginRegistry
from gateway_sdk.core.protocol.commands import AskAgentCommand
from gateway_sdk.core.protocol.content_type import SseMessageType, SseReasonMessageType
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from datacloud_analysis.agent import create_agent


class DataCloudWorker(GatewayWorker):
    """Worker that drives the datacloud-analysis graph inside the gateway_sdk protocol.

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

    # ------------------------------------------------------------------
    # 核心消息处理
    # ------------------------------------------------------------------

    async def process_command(self, command: AskAgentCommand, context: AgentContext) -> dict:
        """Receive a command, run the graph, and stream events back to the caller.

        Args:
            command: 来自 Gateway 的指令，content 为用户消息（str 或 list[dict]）。
            context: 上下文对象，用于 emit_chunk / emit_state / check_cancelled 等。

        Returns:
            {"status": "done"} — 实际内容已通过流式事件发出。
        """
        logger.info(
            "DataCloudWorker.process_command: session=%s content_type=%s",
            context.session_id,
            type(command.content).__name__,
        )
        logger.info("DataCloudWorker received content: %s", command.content)

        # ① 同步 Worker 构造参数 → os.environ，确保图内节点 os.getenv 拿到正确值
        if self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key
        if self.base_url:
            os.environ["OPENAI_BASE_URL"] = self.base_url
        if self.model_name:
            os.environ["DATACLOUD_LLM_REASONING_MODEL"] = self.model_name

        # 提取 extra_payload 信息
        extra_payload = getattr(command, "extra_payload", {})
        by_agent_id = extra_payload.get("byAgentId")
        by_agent_name = extra_payload.get("byAgentName")
        logger.info(
            "Agent context: ID=%s (type=%s), Name=%s",
            by_agent_id,
            type(by_agent_id).__name__,
            by_agent_name,
        )

        # 获取当前挂载的 Workspace
        from gateway_sdk.worker.sandbox.hook_sandbox import active_workspace
        workspace_dir = active_workspace.get()
        logger.info("Active workspace for task: %s", workspace_dir)

        # ② 归一化输入；gateway_context 传入供各节点 emit 思考事件
        input_messages = _normalize_messages(command.content)
        state = {
            "messages": input_messages,
            "agent_id": by_agent_id,
            "agent_name": by_agent_name,
            "workspace_dir": workspace_dir,
            "gateway_context": context,
            "plan": [],
            "results": [],
            "intent": "",
            "clarify_needed": False,
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

        # ③ 发送"开始推理"通知
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

        # 设置执行配置，传入线程 ID 用于 checkpoint
        config = {
            "configurable": {
                "thread_id": context.session_id,
            }
        }

        # 去 context map 里寻找被插件注入的热配置
        agent_configs = context.list_agent_configs()
        logger.info(
            "Agent config candidates: count=%d ids=%s",
            len(agent_configs),
            [
                {"agent_id": cfg.agent_id, "type": type(cfg.agent_id).__name__}
                for cfg in agent_configs
            ],
        )
        config_for_this_call = next(
            (cfg for cfg in agent_configs if str(cfg.agent_id) == str(by_agent_id)),
            None
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
                target_graph = self._build_graph()  # 兜底创建
            self.graphs[cache_key] = target_graph
            # LRU 淘汰：超出上限时移除最旧条目
            while len(self.graphs) > self._GRAPH_CACHE_MAX:
                evicted_key, _ = self.graphs.popitem(last=False)
                logger.info(
                    "Graph cache evicted oldest entry: key=%s (cache_size=%d)",
                    evicted_key,
                    len(self.graphs),
                )
        else:
            # 命中缓存：将该条目移到末尾（标记为最近使用）
            self.graphs.move_to_end(cache_key)

        # 确保运行态 state 能拿到当前配置（构图注入 + 运行态兜底）
        state["prompts_overwrite"] = prompts_dict
        state["dynamic_tools"] = tools_dict

        # ④ 流式驱动 target_graph：
        #    - insight 节点的 LLM token → ANSWER_DELTA（打字机效果）
        #    - 工具起止 → TASK_CREATE / STEP_COMPLETE
        #    - 各节点思考事件已由节点内部直接 emit，worker 不再重复处理
        async for event in target_graph.astream_events(state, config=config, version="v2"):
            await context.check_cancelled()
            kind: str = event["event"]

            if kind == "on_chat_model_stream":
                # insight_node 自己通过 context.emit_chunk 推送三段式回复（Part1/2/3），
                # worker 不再转发，避免 Part1 重复发送。
                pass

            elif kind == "on_tool_start":
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

        # ⑤ 推理结束由 insight_node 在首次 answerDelta 之前发出（见 insight._emit_reasoning_log_end_before_answer）

        # ⑥ 回答结束通知
        await context.emit_chunk(
            StreamChunkEvent(content="回答完成"),
            event_type=EventType.APP_STREAM_RESPONSE.value,
            content_type=SseMessageType.text.value,
        )

        # ⑦ 将流式内容整合写入历史
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
