"""知识构建模块共享 FastAPI 依赖。"""

from __future__ import annotations

from ..file_store import FileManager, FileStoreSettings


def get_file_manager() -> FileManager:
    """FastAPI 依赖：按环境变量创建 FileManager 实例。

    Returns:
        根据 FileStoreSettings 配置初始化的 FileManager。
    """
    return FileManager.from_settings(FileStoreSettings())
