"""
知识注入中间件

在每次模型调用前自动检索并注入本体 Schema。
"""

from __future__ import annotations
from typing import Any, Callable, Optional, Awaitable
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
from deepagents.middleware._utils import append_to_system_message

from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)


class KnowledgeInjectionMiddleware(AgentMiddleware):
    """
    知识注入中间件

    在每次模型调用前自动检索相关本体 Schema 并注入到系统提示中。
    对应重构方案 §3.1.4.4 自定义 Middleware 2
    """

    tools: list = []

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        """在模型调用前注入本体知识。"""
        # 提取最后一条用户消息作为查询
        user_query = ""
        for msg in reversed(request.messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    user_query = content
                break

        if user_query:
            try:
                schema_context = await self._retrieve_schema(user_query)
                if schema_context:
                    new_system = append_to_system_message(request.system_message, schema_context)
                    request = request.override(system_message=new_system)
                    logger.info("KnowledgeInjectionMiddleware: injected schema context")
            except Exception as exc:
                logger.warning("KnowledgeInjectionMiddleware: failed to inject schema: %s", exc)

        return await handler(request)

    async def _retrieve_schema(self, query: str) -> Optional[str]:
        """
        检索相关的本体 Schema。

        Args:
            query: 用户查询

        Returns:
            Schema 上下文字符串，如果没有找到则返回 None
        """
        try:
            result = await search_knowledge.ainvoke({"query": query})

            if not result or not isinstance(result, dict):
                return None

            term_matches = result.get("term_matches", [])
            if not term_matches:
                return None

            schema_lines = ["<ontology_context>"]
            schema_lines.append("相关本体术语：")

            for match in term_matches[:5]:
                term_name = match.get("term_name", "")
                term_type = match.get("term_type_code", "")
                match_type = match.get("match_type", "")

                if term_name:
                    schema_lines.append(f"- {term_name} ({term_type}) [匹配类型: {match_type}]")

            schema_lines.append("</ontology_context>")
            return "\n".join(schema_lines)

        except Exception as exc:
            logger.warning("_retrieve_schema failed: %s", exc)
            return None
