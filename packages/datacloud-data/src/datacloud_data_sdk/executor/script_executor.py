"""
脚本执行器模块

本模块提供 Python 脚本的执行能力，用于执行与动作绑定的脚本代码。
脚本在沙箱环境中执行，支持注入上下文和外部依赖。

脚本约定：
- 必须定义 `def execute(params: dict) -> dict` 函数
- 函数接收参数字典，返回结果字典

注入环境：
- context: RequestContext，当前请求上下文
- loader: OntologyLoader，本体加载器（可选）
- httpx: HTTP 客户端模块（如果已安装）

使用示例：
    executor = ScriptExecutor(ontology_loader)
    result = await executor.execute(script_code, {"param1": "value1"})
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import ScriptExecutionError


class ScriptExecutor:
    """
    脚本执行器

    执行预定义的 Python 脚本代码，支持超时控制和错误处理。

    Attributes:
        _loader: 本体加载器引用，可注入到脚本环境中

    Example:
        executor = ScriptExecutor(loader)
        result = await executor.execute(
            "def execute(params): return {'result': params['x'] * 2}",
            {"x": 5}
        )
    """

    def __init__(self, ontology_loader: Any = None) -> None:
        """
        初始化脚本执行器

        Args:
            ontology_loader: 本体加载器实例，可选注入到脚本环境
        """
        self._loader = ontology_loader

    async def execute(
        self,
        script: str,
        params: dict[str, Any],
        action_code: str = "<inline>",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        编译并执行脚本

        执行流程：
        1. 获取当前请求上下文
        2. 构建脚本命名空间，注入依赖
        3. 编译并执行脚本
        4. 调用 execute 函数获取结果

        Args:
            script: Python 脚本代码
            params: 传递给 execute 函数的参数
            action_code: 动作代码，用于错误信息
            timeout: 执行超时时间（秒）

        Returns:
            dict: execute 函数返回的结果字典

        Raises:
            ScriptExecutionError: 脚本语法错误、执行错误或超时时抛出
        """
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
