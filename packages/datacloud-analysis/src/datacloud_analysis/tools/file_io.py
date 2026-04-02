from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from langchain_core.tools import tool

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)

def _resolve_safe_path(path: str, workspace_dir: str | None) -> Path:
    """Resolve path within workspace_dir. Raises ValueError if escaping."""
    workspace_root = resolve_shared_workspace_dir(workspace_dir)
    p = Path(path)
    if not p.is_absolute() and workspace_root:
        p = workspace_root / p
    p = p.resolve()
    if workspace_root:
        ws = workspace_root.resolve()
        try:
            p.relative_to(ws)
        except ValueError:
            raise ValueError(f"Path {path!r} is outside workspace_dir {workspace_dir!r}")
    return p

@tool("read_file")
async def read_file(path: str, encoding: str = "utf-8") -> str:
    """读取 workspace 内指定文件，返回文本内容。

    Args:
        path: 文件路径（相对于 workspace_dir 或绝对路径）
        encoding: 文件编码，默认 utf-8
    """
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    try:
        resolved = _resolve_safe_path(path, workspace_dir)
    except ValueError as e:
        return f"错误：{e}"
    if not resolved.exists():
        return f"错误：文件不存在 {path}"
    if not resolved.is_file():
        return f"错误：路径不是文件 {path}"
    try:
        return resolved.read_text(encoding=encoding)
    except Exception as exc:
        logger.error("read_file failed path=%s error=%s", path, exc)
        return f"错误：读取失败 {exc}"

@tool("write_file")
async def write_file(path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
    """将内容写入 workspace 内指定文件（自动创建父目录）。

    Args:
        path: 文件路径（相对于 workspace_dir 或绝对路径）
        content: 要写入的文本内容
        encoding: 文件编码，默认 utf-8

    Returns:
        {"success": bool, "path": str, "size": int}
    """
    workspace_dir = os.getenv("DATACLOUD_ACTIVE_WORKSPACE")
    try:
        resolved = _resolve_safe_path(path, workspace_dir)
    except ValueError as e:
        return {"success": False, "error": str(e), "path": path}
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding=encoding)
        return {"success": True, "path": str(resolved), "size": len(content)}
    except Exception as exc:
        logger.error("write_file failed path=%s error=%s", path, exc)
        return {"success": False, "error": str(exc), "path": path}
