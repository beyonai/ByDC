from __future__ import annotations

import asyncio
import contextlib
import importlib
import io
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from langchain_core.tools import tool

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)


def _workspace_root_path(workspace_dir: str | None) -> Path | None:
    raw = resolve_shared_workspace_dir(workspace_dir)
    if raw is None:
        return None
    return Path(str(raw))


def _resolve_safe_path(filename: str, workspace_dir: str | None) -> Path:
    workspace_root = _workspace_root_path(workspace_dir)
    path = Path(filename)
    if not path.is_absolute() and workspace_root:
        path = workspace_root / path
    path = path.resolve()
    if workspace_root:
        workspace = workspace_root.resolve()
        try:
            path.relative_to(workspace)
        except ValueError as err:
            raise ValueError(
                f"Path {filename!r} is outside workspace_dir {workspace_dir!r}"
            ) from err
    return path


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


def _safe_json_dumps(module: ModuleType, value: Any) -> str:
    dumps_obj = module.__dict__.get("dumps")
    if not callable(dumps_obj):
        raise TypeError("json module has no callable dumps().")
    payload = dumps_obj(value, ensure_ascii=False, default=str)
    if not isinstance(payload, str):
        raise TypeError("json.dumps() did not return a string payload.")
    return payload


@tool("write_code")
async def write_code(filename: str, code: str) -> dict[str, Any]:
    """Write Python source into workspace."""
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    if not filename.endswith(".py"):
        filename = f"{filename}.py"

    try:
        resolved = _resolve_safe_path(filename, workspace_dir)
    except ValueError as err:
        return {"success": False, "error": str(err), "path": filename}

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(code, encoding="utf-8")
        logger.info("[write_code] written: %s (%d chars)", resolved, len(code))
        return {"success": True, "path": str(resolved)}
    except Exception as exc:  # noqa: BLE001
        logger.error("write_code failed filename=%s error=%s", filename, exc)
        return {"success": False, "error": str(exc), "path": filename}


@tool("execute_code")
async def execute_code(filename: str, timeout: int = 120) -> dict[str, Any]:  # noqa: ASYNC109
    """Execute one Python file in workspace and return output/result."""
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    if not filename.endswith(".py"):
        filename = f"{filename}.py"

    try:
        resolved = _resolve_safe_path(filename, workspace_dir)
    except ValueError as err:
        return {"exit_code": 1, "output": str(err), "result": None}

    if not resolved.exists():
        return {"exit_code": 1, "output": f"File does not exist: {filename}", "result": None}

    code = resolved.read_text(encoding="utf-8")

    def _run() -> dict[str, Any]:
        stdout_buf = io.StringIO()
        json_module, pandas_module = _load_optional_modules()
        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "json": json_module,
            "pd": pandas_module,
        }

        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, namespace)  # noqa: S102
            result_obj = namespace.get("_result")

            if result_obj is not None and json_module is not None:
                with contextlib.suppress(Exception):
                    json_path = resolved.with_suffix(".json")
                    payload = _safe_json_dumps(json_module, result_obj)
                    json_path.write_text(payload, encoding="utf-8")

            return {
                "exit_code": 0,
                "output": stdout_buf.getvalue(),
                "result": result_obj,
                "result_file": str(resolved.with_suffix(".json")) if result_obj is not None else None,
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
        result = await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=float(timeout))
    except TimeoutError:
        result = {
            "exit_code": 1,
            "output": f"Execution timeout ({timeout}s).",
            "result": None,
        }

    logger.info("[execute_code] file=%s exit_code=%d", filename, result["exit_code"])
    return result
