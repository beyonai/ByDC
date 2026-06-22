from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from datacloud_data_sdk.context import (
    get_current_context,  # TODO(Phase 3): pass InvocationContext explicitly
)
from datacloud_data_sdk.file_storage import (  # TODO(Phase 3): use platform.storage.store_result/get_result
    LocalResultFileStorage,
    ResultFileStorage,
)
from datacloud_platform.errors import DatacloudError
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _resolve_skill_workspace_dir() -> str:
    """从 InvocationContext.extras 取 skill_workspace_dir；非 skill 请求返回空字符串。"""
    try:
        ctx = get_current_context()
        extras = getattr(ctx, "extras", None) or {}
        return str(extras.get("skill_workspace_dir") or "").strip()
    except DatacloudError:
        return ""


def _resolve_workspace_dir() -> str:
    """从 InvocationContext 取 workspace_dir，缺失时退化到当前工作目录。"""
    try:
        ctx = get_current_context()
    except DatacloudError:
        return os.getcwd()

    workspace_dir = str(getattr(ctx, "workspace_dir", "") or "").strip()
    return workspace_dir or os.getcwd()


def _resolve_storage() -> ResultFileStorage:
    """优先取 InvocationContext 注入的 ResultFileStorage；否则降级到 LocalResultFileStorage。

    LocalResultFileStorage 内部会从 context 拿 workspace_dir / user_id / session_id 做
    会话级隔离，并通过 normalize_logical_file_path 拒绝 ``..`` 越权路径。
    """
    try:
        ctx = get_current_context()
    except DatacloudError:
        ctx = None

    storage = getattr(ctx, "result_file_storage", None) if ctx is not None else None
    if isinstance(storage, ResultFileStorage):
        return storage

    return LocalResultFileStorage(_resolve_workspace_dir())


@tool("read_file")
async def read_file(
    path: str,
    begin_line: int = 0,
    end_line: int = -1,
    encoding: str = "utf-8",  # noqa: ARG001 - 预留参数，当前后端统一 utf-8
) -> str:
    """读取 workspace 内指定文件，返回文本内容。

    Args:
        path: 文件路径（必填）。必须是具体的文件路径，例如 "result.csv" 或 "/output/report.txt"。
            不能为空字符串、"/" 或纯目录路径。路径相对于 workspace_dir，或使用绝对逻辑路径。
        begin_line: 起始行号（0 起，含），默认 0；与 ``end_line`` 同时为默认值时返回全文
        end_line: 结束行号（不含），-1 表示读到文件末尾，默认 -1
        encoding: 预留参数，当前 ResultFileStorage 抽象固定使用 utf-8

    不传 ``begin_line`` 和 ``end_line`` 则返回文件全部内容。
    """
    logger.info("read_file called: path=%r begin_line=%d end_line=%d", path, begin_line, end_line)

    # skill 路径分支：直接读本地磁盘
    skill_workspace_dir = _resolve_skill_workspace_dir()
    if skill_workspace_dir:
        skill_dir = Path(skill_workspace_dir).resolve()  # noqa: ASYNC240
        target = Path(path) if Path(path).is_absolute() else (skill_dir / path)  # noqa: ASYNC240
        try:
            target = target.resolve()
            target.relative_to(skill_dir)  # 路径安全校验：必须在 skill_workspace_dir 内
        except ValueError:
            return f"错误：路径 {path} 超出 skill 工作目录范围"
        if not target.exists():
            return f"错误：文件不存在 {path}"
        try:
            content = target.read_text(encoding="utf-8")
            if begin_line <= 0 and end_line < 0:
                return content
            lines = content.splitlines()
            start = max(begin_line, 0)
            stop = len(lines) if end_line < 0 else min(end_line, len(lines))
            return "\n".join(lines[start:stop])
        except OSError as exc:
            return f"错误：读取失败 {exc}"

    # 原有逻辑（不变）
    storage = _resolve_storage()
    try:
        content = storage.read_text(path, begin_line=begin_line, end_line=end_line)
    except ValueError as exc:
        logger.error("read_file ValueError: path=%r error=%s", path, exc)
        return f"错误：{exc}"
    except (OSError, httpx.HTTPError) as exc:
        logger.error("read_file failed path=%r error=%s", path, exc)
        return f"错误：读取失败 {exc}"

    if content is None:
        return f"错误：文件不存在 {path}"
    return content
