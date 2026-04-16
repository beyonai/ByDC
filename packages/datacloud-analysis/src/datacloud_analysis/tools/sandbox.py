"""Sandbox tools.

.. deprecated::
    ``sbx_read_file`` / ``sbx_write_file`` 未被 Agent 挂载，已由
    ``tools/file_io.py`` 中的 ``read_file`` / ``write_file`` 接管。
    ``sbx_run_code`` 同样未挂载，属历史遗留。
    计划在下一个 major 版本移除整个模块。

Tools:
- ``sbx_run_code``: execute Python code in-process with bounded imports.
- ``sbx_read_file``: read a file under sandbox root for one task.
- ``sbx_write_file``: write a file under sandbox root for one task.
"""

from __future__ import annotations

import asyncio
import base64
import builtins
import contextlib
import importlib
import io
import logging
import os
import warnings
from pathlib import Path
from types import ModuleType
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

warnings.warn(
    "datacloud_analysis.tools.sandbox is deprecated and will be removed in the next major version. "
    "Use read_file / write_file from datacloud_analysis.tools.file_io instead.",
    DeprecationWarning,
    stacklevel=2,
)

_DEFAULT_SANDBOX_ROOT = ".datacloud_sandbox"
_DEFAULT_TASK_BUCKET = "_default"
_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "collections",
        "datetime",
        "itertools",
        "json",
        "math",
        "pandas",
        "statistics",
    }
)
_SAFE_BUILTINS: dict[str, Any] = {
    "abs": builtins.abs,
    "all": builtins.all,
    "any": builtins.any,
    "bool": builtins.bool,
    "dict": builtins.dict,
    "enumerate": builtins.enumerate,
    "Exception": builtins.Exception,
    "filter": builtins.filter,
    "float": builtins.float,
    "int": builtins.int,
    "len": builtins.len,
    "list": builtins.list,
    "map": builtins.map,
    "max": builtins.max,
    "min": builtins.min,
    "print": builtins.print,
    "range": builtins.range,
    "round": builtins.round,
    "set": builtins.set,
    "sorted": builtins.sorted,
    "str": builtins.str,
    "sum": builtins.sum,
    "tuple": builtins.tuple,
    "zip": builtins.zip,
}


def _restricted_import(
    name: str,
    globals_: dict[str, Any] | None = None,
    locals_: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> ModuleType:
    root = name.split(".", 1)[0]
    if root not in _ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"Import '{root}' is not allowed in sandbox execution.")
    return builtins.__import__(name, globals_, locals_, fromlist, level)


def _sandbox_task_root(task_id: str) -> Path:
    base = Path(os.getenv("DATACLOUD_SANDBOX_ROOT", _DEFAULT_SANDBOX_ROOT)).resolve()
    task_bucket = task_id.strip() or _DEFAULT_TASK_BUCKET
    return (base / task_bucket).resolve()


def _resolve_sandbox_path(path: str, task_id: str) -> Path:
    rel = Path(path)
    if rel.is_absolute():
        raise ValueError(f"Path {path!r} must be relative to the sandbox task root.")

    root = _sandbox_task_root(task_id)
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as err:
        raise ValueError(f"Path {path!r} is outside sandbox root {root!s}.") from err
    return resolved


def _load_optional_modules() -> tuple[ModuleType | None, ModuleType | None]:
    json_module: ModuleType | None
    pandas_module: ModuleType | None
    try:
        json_module = importlib.import_module("json")
        pandas_module = importlib.import_module("pandas")
    except ImportError:
        json_module = None
        pandas_module = None
    return json_module, pandas_module


@tool
async def sbx_run_code(
    code: str,
    language: str = "python",
    timeout: int = 120,  # noqa: ASYNC109
    task_id: str = "",
    input_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute Python code with a constrained global namespace."""
    if language != "python":
        return {
            "exit_code": 1,
            "output": f"Unsupported language: {language}. Only 'python' is supported.",
            "result": None,
        }

    def _run() -> dict[str, Any]:
        stdout_buf = io.StringIO()
        json_module, pandas_module = _load_optional_modules()
        sandbox_builtins = dict(_SAFE_BUILTINS)
        sandbox_builtins["__import__"] = _restricted_import

        namespace: dict[str, Any] = {
            "__builtins__": sandbox_builtins,
            "input_files": input_files or {},
            "json": json_module,
            "pd": pandas_module,
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
    except TimeoutError:
        result = {
            "exit_code": 1,
            "output": f"Execution timeout ({timeout}s). Please simplify computation.",
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
    """Read one file under the sandbox task directory.

    Returns UTF-8 text when possible; otherwise returns ``base64:<payload>``.
    """
    resolved = _resolve_sandbox_path(path, task_id)
    if not resolved.exists():
        raise FileNotFoundError(f"Sandbox file does not exist: {path}")
    if not resolved.is_file():
        raise ValueError(f"Sandbox path is not a file: {path}")

    data = await asyncio.to_thread(resolved.read_bytes)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "base64:" + base64.b64encode(data).decode("ascii")


@tool
async def sbx_write_file(path: str, content: str, task_id: str = "") -> str:
    """Write one UTF-8 text file under the sandbox task directory.

    Returns the absolute written path.
    """
    resolved = _resolve_sandbox_path(path, task_id)
    await asyncio.to_thread(resolved.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(resolved.write_text, content, encoding="utf-8")
    return str(resolved)
