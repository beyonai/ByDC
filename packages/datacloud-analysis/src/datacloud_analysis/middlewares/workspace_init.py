"""
工作区初始化中间件

将工作区路径、Agent 名称等信息注入到系统提示。
"""

from __future__ import annotations
from typing import Any, Callable
import logging

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
from deepagents.middleware._utils import append_to_system_message

logger = logging.getLogger(__name__)


class WorkspaceInitMiddleware(AgentMiddleware):
    """
    工作区初始化中间件

    将工作区路径、Agent 名称等信息注入到系统提示中。
    对应重构方案 §3.1.4.4 自定义 Middleware 3
    """

    tools: list = []

    def __init__(self, workspace_dir: str, agent_name: str = "DataCloud Agent"):
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self._injected = False  # 只注入一次

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """在第一次模型调用时注入工作区信息。"""
        if not self._injected:
            workspace_info = (
                f"工作区信息：\n- Agent 名称: {self.agent_name}\n- 工作目录: {self.workspace_dir}"
            )
            new_system = append_to_system_message(request.system_message, workspace_info)
            request = request.override(system_message=new_system)
            self._injected = True
            logger.info(
                "WorkspaceInitMiddleware: injected workspace=%s agent=%s",
                self.workspace_dir,
                self.agent_name,
            )

        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        """异步版本：在第一次模型调用时注入工作区信息。"""
        if not self._injected:
            workspace_info = (
                f"工作区信息：\n- Agent 名称: {self.agent_name}\n- 工作目录: {self.workspace_dir}"
            )
            new_system = append_to_system_message(request.system_message, workspace_info)
            request = request.override(system_message=new_system)
            self._injected = True
            logger.info(
                "WorkspaceInitMiddleware: injected workspace=%s agent=%s",
                self.workspace_dir,
                self.agent_name,
            )

        return await handler(request)
