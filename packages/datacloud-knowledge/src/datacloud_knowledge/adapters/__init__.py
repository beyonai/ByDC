"""后端适配器层 — 工厂 + 注册表，内部模块通过字符串选择后端。

不直接导出具体类。内部调用方通过 create_reader/create_engine/create_writer 获取实例：

    from datacloud_knowledge.adapters import create_reader
    reader = create_reader()           # 默认 "opengauss"
    reader = create_reader("mysql")    # 🆕 新增后端

新增后端：实现 contracts/ 中的协议，在此注册即可。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_knowledge.contracts.protocols import TermReader, TermSearchEngine, TermWriter

logger = logging.getLogger(__name__)

_ENV_BACKEND = "DATACLOUD_KNOWLEDGE_BACKEND"
_DEFAULT_BACKEND = "opengauss"

# ── 注册表 — 新增后端在此添加 ─────────────────────────────────────────

_reader_registry: dict[str, type[TermReader]] = {}
_engine_registry: dict[str, type[TermSearchEngine]] = {}
_writer_registry: dict[str, type[TermWriter]] = {}


def _register_opengauss() -> None:
    """注册 OpenGauss 后端（延迟导入避免循环依赖）。"""
    from datacloud_knowledge.adapters.opengauss.engine import PostgresSearchEngine
    from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
    from datacloud_knowledge.adapters.opengauss.writer import PostgresTermWriter

    _reader_registry.setdefault("opengauss", PostgresTermReader)
    _engine_registry.setdefault("opengauss", PostgresSearchEngine)
    _writer_registry.setdefault("opengauss", PostgresTermWriter)


def _resolve_backend(backend: str | None = None) -> str:
    """解析后端标识：显式传入 > 环境变量 > 默认值。"""
    return backend or os.getenv(_ENV_BACKEND, _DEFAULT_BACKEND)


# ── 工厂函数 — 内部模块调用入口 ────────────────────────────────────────


def create_reader(backend: str | None = None) -> TermReader:
    """创建术语读取器实例。

    Args:
        backend: 后端标识（"opengauss"/"mysql"），默认读环境变量。

    Returns:
        实现了 TermReader 协议的读取器实例。
    """
    resolved = _resolve_backend(backend)
    if resolved not in _reader_registry:
        _register_opengauss()
    cls = _reader_registry.get(resolved)
    if cls is None:
        available = sorted(_reader_registry)
        raise ValueError(f"不支持的后端: {resolved!r}，可用: {available}")
    return cls()


def create_engine(backend: str | None = None) -> TermSearchEngine:
    """创建检索引擎实例。"""
    resolved = _resolve_backend(backend)
    if resolved not in _engine_registry:
        _register_opengauss()
    cls = _engine_registry.get(resolved)
    if cls is None:
        available = sorted(_engine_registry)
        raise ValueError(f"不支持的后端: {resolved!r}，可用: {available}")
    return cls()


def create_writer(backend: str | None = None) -> TermWriter:
    """创建术语写入器实例。"""
    resolved = _resolve_backend(backend)
    if resolved not in _writer_registry:
        _register_opengauss()
    cls = _writer_registry.get(resolved)
    if cls is None:
        available = sorted(_writer_registry)
        raise ValueError(f"不支持的后端: {resolved!r}，可用: {available}")
    return cls()
