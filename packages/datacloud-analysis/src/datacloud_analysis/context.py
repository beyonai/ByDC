"""DatacloudContext — Gateway 运行时上下文 schema。

替代通过 config["configurable"] 传递的非类型化字典，提供类型安全的上下文注入。
通过 create_deep_agent(context_schema=DatacloudContext) 注册，
SDK 自动将 config["configurable"] 中对应字段注入到每个节点。
"""

from __future__ import annotations

from typing import Any

from typing_extensions import NotRequired, TypedDict


class DatacloudContext(TypedDict):
    """传入每个 agent 节点的 gateway 运行时上下文。

    Usage (worker.py 侧)::

        config = {
            "configurable": {
                "thread_id": session_id,
                "gateway_context": context.gateway_context,
                "agent_id": by_agent_id,
                "agent_name": by_agent_name,
                "workspace_dir": workspace_dir,
                "locale": "zh_CN",
                "session_id": session_id,
                "trace_id": trace_id,
            }
        }
    """

    gateway_context: Any
    """gateway emit_chunk / ask_user 句柄（AgentContext 对象）。"""

    agent_id: str
    """数字员工 ID。"""

    agent_name: NotRequired[str]
    """数字员工显示名称。"""

    locale: NotRequired[str]
    """语言区域代码，如 zh_CN / en_US。"""

    workspace_dir: str
    """当前请求的工作区根路径（用于文件读写、落文件分页等）。"""

    session_id: str
    """线程 ID，等同于 LangGraph thread_id，作为 checkpointer 的 key。"""

    trace_id: NotRequired[str]
    """请求追踪 ID（用于日志关联）。"""
