from __future__ import annotations

import logging
import os

import httpx
from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import DatacloudError
from datacloud_data_sdk.file_storage import LocalResultFileStorage, ResultFileStorage
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


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
        path: 文件路径（逻辑路径，相对于 workspace_dir 或绝对逻辑路径）
        begin_line: 起始行号（0 起，含），默认 0；与 ``end_line`` 同时为默认值时返回全文
        end_line: 结束行号（不含），-1 表示读到文件末尾，默认 -1
        encoding: 预留参数，当前 ResultFileStorage 抽象固定使用 utf-8

    不传 ``begin_line`` 和 ``end_line`` 则返回文件全部内容。
    """
    storage = _resolve_storage()
    try:
        content = storage.read_text(path, begin_line=begin_line, end_line=end_line)
    except ValueError as exc:
        return f"错误：{exc}"
    except (OSError, httpx.HTTPError) as exc:
        logger.error("read_file failed path=%s error=%s", path, exc)
        return f"错误：读取失败 {exc}"

    if content is None:
        return f"错误：文件不存在 {path}"
    return content
