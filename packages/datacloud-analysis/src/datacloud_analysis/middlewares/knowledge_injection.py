"""
知识注入中间件

在每次模型调用前（每个问题时）注入本体 Schema。
"""

from __future__ import annotations
from typing import Any, Callable, Awaitable
import logging

from langchain_core.messages import HumanMessage
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
from deepagents.middleware._utils import append_to_system_message

logger = logging.getLogger(__name__)


class KnowledgeInjectionMiddleware(AgentMiddleware):
    """
    知识注入中间件

    在每次 LLM 调用时（每个问题）注入本体 Schema，支持未来精细化过滤。
    使用 LangGraph state 去重，避免重复注入。
    """

    tools: list = []

    def __init__(self, mounted_objects: list[str] | None = None):
        """
        Args:
            mounted_objects: 挂载的对象/视图列表（完整列表）
        """
        super().__init__()
        self.mounted_objects = mounted_objects or []

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        """在 LLM 调用前注入本体 Schema。"""
        # 去重检查：使用 LangGraph state（持久化到 checkpoint）
        state = request.runtime.state
        if state.get("_ontology_injected", False):
            # 已注入，跳过
            return await handler(request)

        if not self.mounted_objects:
            # 没有挂载对象，跳过
            return await handler(request)

        try:
            # 1. 提取用户问题
            user_query = self._extract_user_query(request)

            # 2. 精细化过滤（根据用户问题筛选相关对象）
            #    TODO: 待罗彦卓实现，当前返回所有挂载对象
            relevant_objects = self._filter_relevant_objects(user_query, self.mounted_objects)

            # 3. 构建 Schema
            ontology_schema = await self._build_ontology_schema(relevant_objects)

            if ontology_schema:
                # 4. 注入到 system_message
                updated_request = request.override(
                    system_message=append_to_system_message(
                        request.system_message,
                        ontology_schema
                    )
                )

                # 5. 标记已注入（写入 state）
                state["_ontology_injected"] = True

                logger.info(
                    "KnowledgeInjectionMiddleware: injected %d objects: %s",
                    len(relevant_objects),
                    relevant_objects
                )

                # 6. 调用下一个 handler
                return await handler(updated_request)

        except Exception as exc:
            logger.warning("Failed to inject ontology schema: %s", exc)

        return await handler(request)

    def _extract_user_query(self, request: ModelRequest) -> str:
        """从 request 中提取用户问题。"""
        try:
            # 从 messages 中提取最新的用户消息
            messages = request.runtime.state.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    return msg.get("content", "")
                elif isinstance(msg, HumanMessage):
                    content = msg.content
                    if isinstance(content, str):
                        return content
            return ""
        except Exception:
            return ""

    def _filter_relevant_objects(
        self,
        user_query: str,
        all_objects: list[str]
    ) -> list[str]:
        """根据用户问题筛选相关对象（精细化过滤）。

        TODO: 待罗彦卓实现

        未来实现思路：
        1. 使用 search_knowledge 或 LLM 分析用户问题的意图
        2. 识别问题中涉及的对象类型（如"企业"、"订单"等）
        3. 仅返回相关对象的编码列表
        4. 优化场景：当挂载对象数量 > 10 或上下文压力大时启用

        Args:
            user_query: 用户问题
            all_objects: 所有挂载的对象编码列表

        Returns:
            相关对象编码列表（当前返回全部对象）
        """
        # 当前实现：返回所有挂载对象（不做过滤）
        return all_objects

    async def _build_ontology_schema(self, object_codes: list[str]) -> str | None:
        """构建本体 Schema。

        Args:
            object_codes: 要注入的对象编码列表

        Returns:
            格式化的 Schema 字符串，或 None（如果失败）
        """
        try:
            from datacloud_analysis.dependencies import get_oql_router
            from datacloud_analysis.utils.schema_formatter import format_object_schema

            router = get_oql_router()
            ontology_loader = router.ontology_loader

            if not object_codes:
                return None

            # 获取所有关系（一次性查询）
            all_relations = ontology_loader.get_ontology_relations()

            schema_lines = ["<ontology_context>"]
            schema_lines.append("## 可用对象类型（object_type）\n")

            for idx, object_code in enumerate(object_codes[:10], 1):  # 最多10个对象
                try:
                    # 1. 获取对象定义
                    ontology_class = ontology_loader.get_ontology_class(object_code)

                    # 2. 格式化对象 Schema
                    formatted = format_object_schema(
                        ontology_class,
                        all_relations,
                        ontology_loader
                    )
                    schema_lines.append(formatted)

                    if idx < len(object_codes) and idx < 10:
                        schema_lines.append("\n---\n")
                except Exception as e:
                    logger.warning("Failed to load object %s: %s", object_code, e)
                    continue

            schema_lines.append("\n</ontology_context>")
            return "\n".join(schema_lines)

        except Exception as e:
            logger.warning("Failed to build ontology schema: %s", e)
            return None
