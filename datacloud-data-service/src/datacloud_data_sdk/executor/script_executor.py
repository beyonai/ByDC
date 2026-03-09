"""ScriptExecutor: 执行与动作绑定的 Python 脚本。

脚本约定：必须定义 def execute(params: dict) -> dict
注入环境：context（RequestContext）、loader（OntologyLoader，可选）、httpx 模块
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import ScriptExecutionError


class ScriptExecutor:
    """执行预定义 Python 脚本的执行器。"""

    def __init__(self, ontology_loader: Any = None) -> None:
        self._loader = ontology_loader

    async def execute(
        self,
        script: str,
        params: dict[str, Any],
        action_code: str = "<inline>",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """编译并执行脚本，返回结果 dict。"""
        try:
            ctx = get_current_context()
        except Exception:
            ctx = None

        namespace: dict[str, Any] = {
            "context": ctx,
            "loader": self._loader,
        }

        try:
            import httpx

            namespace["httpx"] = httpx
        except ImportError:
            pass

        try:
            exec(compile(script, f"<action:{action_code}>", "exec"), namespace)
        except SyntaxError as e:
            raise ScriptExecutionError(action_code, f"SyntaxError: {e}", line_no=e.lineno)

        execute_fn = namespace.get("execute")
        if execute_fn is None or not callable(execute_fn):
            raise ScriptExecutionError(
                action_code,
                "Script must define `def execute(params: dict) -> dict`",
            )

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, execute_fn, params),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise ScriptExecutionError(action_code, f"Script timed out after {timeout}s")
        except ScriptExecutionError:
            raise
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            line_no = tb[-1].lineno if tb else None
            raise ScriptExecutionError(action_code, str(e), line_no=line_no)

        if not isinstance(result, dict):
            raise ScriptExecutionError(
                action_code,
                f"execute() must return dict, got {type(result).__name__}",
            )
        return result
