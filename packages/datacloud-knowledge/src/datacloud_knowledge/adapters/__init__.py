"""后端适配器层 — 工厂 + 注册表，内部模块通过字符串选择后端。

不直接导出具体类。内部调用方通过 create_reader/create_engine/create_writer 获取实例：

    from datacloud_knowledge.adapters import create_reader
    reader = create_reader()           # 默认 "opengauss"
    reader = create_reader("mysql")    # 🆕 新增后端

新增后端：实现 contracts/ 中的协议，在此注册即可。


Schema 管理 & Backfill（CLI 入口）：

    from datacloud_knowledge.adapters import ensure_schema, verify_schema
    from datacloud_knowledge.adapters import backfill_tsvector, backfill_embeddings
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    resolved = backend or os.getenv(_ENV_BACKEND)
    return resolved or _DEFAULT_BACKEND


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


def create_engine(
    backend: str | None = None,
    session: Session | None = None,
) -> TermSearchEngine:
    """创建检索引擎实例。

    Args:
        backend: 后端标识（"opengauss"/"mysql"），默认读环境变量。
        session: 可选，SQLAlchemy Session。传入时 engine 绑定该 session，
            调用方负责事务管理。不传时 engine 自行管理 session 生命周期。

    Returns:
        实现了 TermSearchEngine 协议的检索引擎实例。
    """
    resolved = _resolve_backend(backend)
    if resolved not in _engine_registry:
        _register_opengauss()
    cls = _engine_registry.get(resolved)
    if cls is None:
        available = sorted(_engine_registry)
        raise ValueError(f"不支持的后端: {resolved!r}，可用: {available}")
    factory = cast(Callable[..., TermSearchEngine], cls)
    return factory(session=session) if session is not None else factory()


def create_writer(
    backend: str | None = None,
    session: Session | None = None,
) -> TermWriter:
    """创建术语写入器实例。

    Args:
        backend: 后端标识（"opengauss"/"mysql"），默认读环境变量。
        session: 可选，SQLAlchemy Session。传入时 writer 绑定该 session，
            调用方负责事务管理。不传时 writer 自行管理 session 生命周期。

    Returns:
        实现了 TermWriter 协议的写入器实例。
    """
    resolved = _resolve_backend(backend)
    if resolved not in _writer_registry:
        _register_opengauss()
    cls = _writer_registry.get(resolved)
    if cls is None:
        available = sorted(_writer_registry)
        raise ValueError(f"不支持的后端: {resolved!r}，可用: {available}")
    factory = cast(Callable[..., TermWriter], cls)
    return factory(session=session) if session is not None else factory()


def store_clarification_results(
    clarification_results: dict[str, Any],
    user_id: str,
) -> list[str]:
    """持久化澄清结果，自管理 session 和事务。

    遍历 clarification_results，根据 value 类型分发：
    - dict with "term_id" → create_term_name（别名已存在的术语）
    - str → create_term_with_knowledge + create_term_name（新建用户定义术语）

    Args:
        clarification_results: {mention_text: {"term_id": ...} | description_string}
        user_id: 操作用户 ID。

    Returns:
        创建的 name_id 列表。
    """
    created_ids: list[str] = []
    with create_writer() as writer:
        for mention_text, result in clarification_results.items():
            if isinstance(result, dict) and "term_id" in result:
                name_id = writer.create_term_name(
                    term_id=str(result["term_id"]),
                    name_text=mention_text,
                    user_id=user_id,
                    search_scope={},
                )
                created_ids.append(name_id)
            elif isinstance(result, str) and result.strip():
                _term_id = writer.create_term_with_knowledge(
                    term_name=mention_text,
                    term_type_code="USER_DEFINED",
                    library_id=None,  # type: ignore[arg-type]
                    domain_id="DOMAIN_002",
                    knowledge_desc=result,
                    user_id=user_id,
                )
                name_id = writer.create_term_name(
                    term_id=_term_id,
                    name_text=mention_text,
                    user_id=user_id,
                    search_scope={},
                )
                created_ids.append(name_id)
    return created_ids


# ── Schema 管理 & Backfill（CLI 入口）───────────────────────────────────


def ensure_schema(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    reset: bool = False,
    seed: bool = True,
    create_vector_extension: bool = False,
) -> dict[str, Any]:
    """创建或更新知识库表结构。

    Args:
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。
        reset: 是否 drop 后重建（破坏性）。
        seed: 是否插入内置种子数据。
        create_vector_extension: 是否创建 pgvector 扩展。

    Returns:
        dict，字段：status / created / already_existed / errors。
    """
    from datacloud_knowledge.adapters.opengauss._db.schema import (
        ensure_schema as _ensure_schema,
    )

    return _ensure_schema(
        schema=schema,
        db_url=db_url,
        reset=reset,
        seed=seed,
        create_vector_extension=create_vector_extension,
    )


def verify_schema(
    *,
    schema: str | None = None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """验证知识库核心表是否存在。

    Args:
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。

    Returns:
        dict，字段：all_present / tables / missing_tables。
    """
    from datacloud_knowledge.adapters.opengauss._db.schema import (
        verify_schema as _verify_schema,
    )

    return _verify_schema(schema=schema, db_url=db_url)


def backfill_tsvector(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """回填 term_name 表的 tsvector 字段。

    Args:
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。
        force: 是否重新计算所有行（默认仅处理 NULL 行）。

    Returns:
        dict，字段：status / processed / skipped。
    """
    from datacloud_knowledge.adapters.opengauss._db.tsvector import (
        backfill_tsvector_with_url as _backfill_tsvector,
    )

    return _backfill_tsvector(schema=schema, db_url=db_url, force=force)


def backfill_embeddings(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    batch_size: int = 50,
    force: bool = False,
    limit: int | None = None,
    term_ids: list[str] | None = None,
    embedding_api_base: str = "",
    embedding_api_key: str = "",
    embedding_model: str = "",
) -> dict[str, Any]:
    """回填 term_name 表的向量嵌入字段。

    Args:
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。
        batch_size: 每次 API 批次处理的 term name 数量。
        force: 是否重新生成所有嵌入（默认仅处理 NULL 嵌入）。
        limit: 最大处理数量（None 表示不限制）。
        term_ids: 限定只回填指定 term_id 的向量（None 表示全部）。
        embedding_api_base: Embedding API URL（覆盖环境变量）。
        embedding_api_key: Embedding API 密钥（覆盖环境变量）。
        embedding_model: Embedding 模型名称（覆盖环境变量）。

    Returns:
        dict，字段：status / processed / skipped。
    """
    from datacloud_knowledge.adapters.opengauss._db.embeddings import (
        backfill_name_embeddings as _backfill_embeddings,
    )

    return _backfill_embeddings(
        schema=schema,
        db_url=db_url,
        batch_size=batch_size,
        force=force,
        limit=limit,
        term_ids=term_ids,
        embedding_api_base=embedding_api_base,
        embedding_api_key=embedding_api_key,
        embedding_model=embedding_model,
    )


# ── 批量导入适配器 ───────────────────────────────────────────────────────


def create_bulk_importer(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    conninfo: str | None = None,
) -> Any:
    """创建批量导入适配器实例。

    封装 psycopg 连接管理和批量写入，导入器不需要直接接触 psycopg。

    Args:
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。
        conninfo: psycopg 连接字符串（可选，优先于 db_url）。

    Returns:
        BulkImportAdapter 实例。
    """
    from datacloud_knowledge.adapters.opengauss.import_writer import (
        BulkImportAdapter,
    )

    return BulkImportAdapter(schema=schema, db_url=db_url, conninfo=conninfo)
