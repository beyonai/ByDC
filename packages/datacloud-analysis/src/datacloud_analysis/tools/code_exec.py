from __future__ import annotations
import asyncio
import contextlib
import io
import logging
import os
from pathlib import Path
from typing import Any
from langchain_core.tools import tool

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)

def _resolve_safe_path(filename: str, workspace_dir: str | None) -> Path:
    workspace_root = resolve_shared_workspace_dir(workspace_dir)
    p = Path(filename)
    if not p.is_absolute() and workspace_root:
        p = workspace_root / p
    p = p.resolve()
    if workspace_root:
        ws = workspace_root.resolve()
        try:
            p.relative_to(ws)
        except ValueError:
            raise ValueError(f"Path {filename!r} is outside workspace_dir {workspace_dir!r}")
    return p

@tool("write_code")
async def write_code(filename: str, code: str) -> dict[str, Any]:
    """将 LLM 生成的 Python 代码写入 workspace 内的 .py 文件。
    执行前请用 execute_code 运行。

    Args:
        filename: 文件名（.py 后缀，相对于 workspace_dir）
        code: Python 源代码

    Returns:
        {"success": bool, "path": str}
    """
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    # 强制 .py 后缀
    if not filename.endswith(".py"):
        filename = filename + ".py"
    try:
        resolved = _resolve_safe_path(filename, workspace_dir)
    except ValueError as e:
        return {"success": False, "error": str(e), "path": filename}
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(code, encoding="utf-8")
        logger.info("[write_code] written: %s (%d chars)", resolved, len(code))
        return {"success": True, "path": str(resolved)}
    except Exception as exc:
        logger.error("write_code failed filename=%s error=%s", filename, exc)
        return {"success": False, "error": str(exc), "path": filename}

@tool("execute_code")
async def execute_code(filename: str, timeout: int = 120) -> dict[str, Any]:
    """执行 workspace 内指定的 .py 文件，返回 exit_code / output / result。

    Args:
        filename: .py 文件名（相对于 workspace_dir）
        timeout: 执行超时秒数，默认 120

    Returns:
        {"exit_code": int, "output": str, "result": Any}
    """
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    if not filename.endswith(".py"):
        filename = filename + ".py"
    try:
        resolved = _resolve_safe_path(filename, workspace_dir)
    except ValueError as e:
        return {"exit_code": 1, "output": str(e), "result": None}

    if not resolved.exists():
        return {"exit_code": 1, "output": f"文件不存在: {filename}", "result": None}

    code = resolved.read_text(encoding="utf-8")

    def _run() -> dict[str, Any]:
        stdout_buf = io.StringIO()
        try:
            import json as _json
            import pandas as _pd
        except ImportError:
            _json = None  # type: ignore
            _pd = None    # type: ignore

        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "json": _json,
            "pd": _pd,
        }
        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, namespace)  # noqa: S102
            _result = namespace.get("_result")
            # 将 _result 序列化到同名 .json 文件，供后续代码读取
            if _result is not None and _json is not None:
                try:
                    json_path = resolved.with_suffix(".json")
                    json_path.write_text(
                        _json.dumps(_result, ensure_ascii=False, default=str),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            return {
                "exit_code": 0,
                "output": stdout_buf.getvalue(),
                "result": _result,
                "result_file": str(resolved.with_suffix(".json")) if _result is not None else None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "exit_code": 1,
                "output": f"{type(exc).__name__}: {exc}\n{stdout_buf.getvalue()}",
                "result": None,
                "result_file": None,
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
            "output": f"执行超时（{timeout}s）",
            "result": None,
        }
    logger.info("[execute_code] file=%s exit_code=%d", filename, result["exit_code"])
    return result
