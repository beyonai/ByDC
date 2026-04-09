"""DatacloudBackend — 将 Deep Agents 文件操作绑定到 workspace_dir。

继承 FilesystemBackend，设定 virtual_mode=True 以拒绝逃出 workspace_dir 的路径（../）。
所有 ls / read_file / write_file / edit_file / glob / grep 工具操作均限定在 workspace_dir 内。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_datacloud_backend(workspace_dir: str | Path) -> Any:
    """创建绑定到 workspace_dir 的 DatacloudBackend 实例。

    Args:
        workspace_dir: 工作区根路径。所有文件操作都限定在此目录内。

    Returns:
        FilesystemBackend 实例（virtual_mode=True，阻止路径逃逸）。

    Example::

        backend = create_datacloud_backend("/tmp/workspace/session-1")
        agent = create_deep_agent(..., backend=backend)
    """
    try:
        from deepagents.backends.filesystem import FilesystemBackend  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "deepagents 未安装，无法创建 DatacloudBackend。请运行: pip install deepagents"
        ) from exc

    root = Path(workspace_dir).resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        logger.info("DatacloudBackend: created workspace directory %s", root)

    logger.info("DatacloudBackend: root=%s virtual_mode=True", root)
    return FilesystemBackend(root_dir=root, virtual_mode=True)
