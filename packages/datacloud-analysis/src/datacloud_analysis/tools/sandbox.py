"""Sandbox tools — T_SBX_RUN / T_SBX_READ / T_SBX_WRITE (design §3.1 / §4.4).

These three tools are the Agent's hands inside the isolated sandbox
(LocalDockerBackend or RemoteDockerBackend).  They map directly to the
three sandbox symbols in the design flowchart.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def sbx_run_code(
    code: str,
    language: str = "python",
    timeout: int = 120,
    task_id: str = "",
    input_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """T_SBX_RUN — execute Python code locally with access to dep task data files.

    Args:
        code:        Python source code to execute.
        language:    Reserved for future use; currently only "python" is supported.
        timeout:     Execution timeout in seconds.
        task_id:     Identifier of the current task (for logging).
        input_files: Mapping of dep task_id → absolute JSONL file path.
                     Available as ``input_files`` variable inside the code.
                     The code may also use ``pd`` (pandas) and ``json`` directly.

    Returns:
        ``{"exit_code": int, "output": str, "result": Any}``
        where ``result`` is the value assigned to ``_result`` inside the code.

    Note:
        Code is executed via ``exec()`` without sandbox isolation.
        Intended for internal / trusted environments only.
    """
    if language != "python":
        return {
            "exit_code": 1,
            "output": f"Unsupported language: {language}. Only 'python' is supported.",
            "result": None,
        }

    def _run() -> dict[str, Any]:
        stdout_buf = io.StringIO()

        # Pre-import common modules so generated code can skip import statements
        try:
            import json as _json
            import pandas as _pd
        except ImportError:
            _json = None  # type: ignore[assignment]
            _pd = None    # type: ignore[assignment]

        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "input_files": input_files or {},
            "json": _json,
            "pd": _pd,
        }

        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, namespace)  # noqa: S102
            return {
                "exit_code": 0,
                "output": stdout_buf.getvalue(),
                "result": namespace.get("_result"),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "exit_code": 1,
                "output": f"{type(exc).__name__}: {exc}\n{stdout_buf.getvalue()}",
                "result": None,
            }

    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=float(timeout),
        )
    except asyncio.TimeoutError:
        result = {
            "exit_code": 1,
            "output": f"执行超时（{timeout}s），请简化计算逻辑或增大 timeout。",
            "result": None,
        }

    logger.info(
        "[sbx_run_code] task_id=%s exit_code=%d output_len=%d",
        task_id or "?",
        result["exit_code"],
        len(result["output"]),
    )
    return result


@tool
async def sbx_read_file(path: str, task_id: str = "") -> str:
    """T_SBX_READ — read a file from the sandbox workspace.

    Args:
        path:    Relative path inside the sandbox (e.g. ``outputs/report.csv``).
        task_id: Used to locate the correct sandbox instance.

    Returns:
        File contents as a string (binary files base64-encoded).
    """
    raise NotImplementedError(
        "sbx_read_file: sandbox backend integration not yet implemented."
    )


@tool
async def sbx_write_file(path: str, content: str, task_id: str = "") -> str:
    """T_SBX_WRITE — write or overwrite a file in the sandbox workspace.

    Args:
        path:    Relative path inside the sandbox.
        content: Text content to write.
        task_id: Used to locate the correct sandbox instance.

    Returns:
        Absolute path of the written file inside the sandbox.
    """
    raise NotImplementedError(
        "sbx_write_file: sandbox backend integration not yet implemented."
    )
