"""DataCloud Gateway Worker.

将 datacloud-analysis LangGraph 接入 gateway_sdk worker 协议：
- 收 AskAgentCommand 消息
- 归一化消息格式，驱动图执行
- 通过 EventType 将 LLM token/工具调用状态实时回传
"""

from __future__ import annotations

from typing import Any, Optional

from gateway_sdk import (
    AgentContext,
    EventType,
    GatewayWorker,
    StateChangeEvent,
    StreamChunkEvent,
)
from gateway_sdk.common.logger import logger
from gateway_sdk.core.extensions import PluginRegistry
from gateway_sdk.core.protocol.commands import AskAgentCommand
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from datacloud_analysis.agent import create_agent


class DataCloudWorker(GatewayWorker):
    """Worker that drives the datacloud-analysis graph inside the gateway_sdk protocol.

    启动时通过 run_worker(**worker_kwargs) 将以下参数透传至 __init__：
        model_name  — LLM 模型名（读自 .env DATACLOUD_LLM_REASONING_MODEL）
        api_key     — OpenAI-compatible API key（读自 .env OPENAI_API_KEY）
        base_url    — OpenAI-compatible base URL（读自 .env OPENAI_BASE_URL）
    """

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
        # 初次构图（测试或预热时可用）
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Instantiate the datacloud-analysis compiled graph."""
        return create_agent(
            model=self.model_name,   # create_agent 内部会自动加 openai: 前缀
            api_key=self.api_key,
            base_url=self.base_url,
        )

    async def start_heartbeat(self) -> None:
        """Worker 启动后（插件 on_startup 完成）重建 graph，确保绑定最新状态。"""
        await super().start_heartbeat()
        
        # 初始化 SDK 环境 (PG 数据库建表, Checkpoint, Memory 等)
        from datacloud_analysis import bootstrap
        await bootstrap.setup()
        
        self.graph = self._build_graph()
        logger.info("DataCloudWorker: graph rebuilt after startup.")

    def get_capabilities(self) -> list[str]:
        """向 gateway 注册本 worker 的能力标签。"""
        return ["datacloud"]

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
        # command.extra_payload.GE
        # 提取 extra_payload 信息
        extra_payload = getattr(command, "extra_payload", {})
        by_agent_id = extra_payload.get("byAgentId")
        by_agent_name = extra_payload.get("byAgentName")
        logger.info("Agent context: ID=%s, Name=%s", by_agent_id, by_agent_name)

        # 获取当前挂载的 Workspace
        from gateway_sdk.worker.sandbox.hook_sandbox import active_workspace
        workspace_dir = active_workspace.get()
        logger.info("Active workspace for task: %s", workspace_dir)

        # ① 归一化输入：将 command.content 转换成 LangChain messages
        input_messages = _normalize_messages(command.content)
        state = {
            "messages": input_messages,
            "agent_id": by_agent_id,
            "agent_name": by_agent_name,
            "workspace_dir": workspace_dir,
            "plan": [],
            "intent": "",
            "clarify_needed": False
        }

        # ② 发送"开始推理"通知
        await context.emit_state(
            StateChangeEvent(state="正在思考..."),
            event_type=EventType.REASONING_LOG_START.value,
        )

        # 设置执行配置，传入线程 ID 用于 checkpoint
        config = {
            "configurable": {
                "thread_id": context.session_id,
            }
        }

        # ③ 流式驱动 graph，将事件映射到 gateway EventType
        async for event in self.graph.astream_events(state, config=config, version="v2"):
            await context.check_cancelled()
            kind: str = event["event"]

            if kind == "on_chat_model_stream":
                # LLM 增量 token → ANSWER_DELTA（打字机效果）
                chunk = event["data"]["chunk"]
                if chunk.content:
                    await context.emit_chunk(
                        StreamChunkEvent(content=chunk.content),
                        event_type=EventType.ANSWER_DELTA.value,
                    )

            elif kind == "on_chat_model_start":
                # 新一轮模型调用开始 → REASONING_LOG_DELTA（可选：展示正在推理）
                await context.emit_state(
                    StateChangeEvent(state="模型推理中..."),
                    event_type=EventType.REASONING_LOG_DELTA.value,
                )

            elif kind == "on_tool_start":
                # 工具开始调用 → TASK_CREATE（展示正在执行哪个工具）
                tool_name: str = event.get("name", "unknown_tool")
                await context.emit_state(
                    StateChangeEvent(state=f"调用工具: {tool_name}"),
                    event_type=EventType.TASK_CREATE.value,
                )

            elif kind == "on_tool_end":
                # 工具结束 → STEP_COMPLETE
                tool_name = event.get("name", "unknown_tool")
                await context.emit_state(
                    StateChangeEvent(state=f"工具完成: {tool_name}"),
                    event_type=EventType.STEP_COMPLETE.value,
                )

        # ④ 推理结束通知
        await context.emit_state(
            StateChangeEvent(state="回答完成"),
            event_type=EventType.REASONING_LOG_END.value,
        )

         # ④ 回答结束通知
        await context.emit_state(
            StateChangeEvent(state="回答完成"),
            event_type=EventType.APP_STREAM_RESPONSE.value,
        )

        # ⑤ 将流式内容整合写入历史
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
