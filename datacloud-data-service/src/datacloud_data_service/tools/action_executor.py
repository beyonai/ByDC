"""ActionExecutor: 操作类工具的执行流水线。"""

from __future__ import annotations

import json
from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_service.tools.param_mapper import ParamMapper
from datacloud_data_service.tools.term_resolver import TermResolver


class ActionExecutor:
    """操作类工具执行流水线。

    虚拟动作：resolve_filter_values → Object.invoke_action
    真实动作：ParamMapper → TermResolver → Object.invoke_action
    统一走 obj.invoke_action，Action 内部分发。
    """

    def __init__(
        self,
        loader: OntologyLoader,
        term_loader: TermLoader | None = None,
    ) -> None:
        self._loader = loader
        self._term_resolver = TermResolver(term_loader)

    async def execute(
        self,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """执行操作类动作，返回 MCP content 格式。"""
        cls = self._loader.get_ontology_class(object_code)
        action = None
        for a in cls.actions:
            if a.action_code == action_code:
                action = a
                break
        if action is None:
            from datacloud_data_sdk.exceptions import ActionNotFoundError

            raise ActionNotFoundError(object_code, action_code)

        if getattr(action, "is_virtual", False):
            filters = self._term_resolver.resolve_filter_values(
                arguments.get("filters", {}),
                cls.fields,
            )
            params = {**arguments, "filters": filters}
        else:
            mapper = ParamMapper(action)
            params = mapper.map_names(arguments)
            params = self._term_resolver.resolve(action, params)
            params = mapper.map_to_physical(params)

        obj = self._loader.get_object(object_code)
        result = await obj.invoke_action(action_code, params)

        return {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
            ],
            "isError": False,
        }
