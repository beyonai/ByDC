"""统一数据库基础设施层。"""

from typing import Any

from .url import (
    ParsedDatabaseUrl,
    build_postgres_connection_uri,
    build_sqlalchemy_database_config,
    infer_database_type_from_url,
    parse_database_url,
    parse_env_database_url,
    resolve_knowledge_schema,
    resolve_knowledge_schema_for_connection,
    validate_schema_name,
)

_LAZY_EXPORTS = {
    "DatabaseContext": ("datacloud_knowledge.adapters.opengauss._db.context", "DatabaseContext"),
    "Term": ("datacloud_knowledge.adapters.opengauss._db.models", "Term"),
    "TermRelation": ("datacloud_knowledge.adapters.opengauss._db.models", "TermRelation"),
    "TermType": ("datacloud_knowledge.adapters.opengauss._db.models", "TermType"),
    "get_session": ("datacloud_knowledge.adapters.opengauss._db.connection", "get_session"),
}


def __getattr__(name: str) -> Any:
    """Lazily import SQLAlchemy-backed database helpers."""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'datacloud_knowledge.db' has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "DatabaseContext",
    "ParsedDatabaseUrl",
    "Term",
    "TermRelation",
    "TermType",
    "build_postgres_connection_uri",
    "build_sqlalchemy_database_config",
    "get_session",
    "infer_database_type_from_url",
    "parse_database_url",
    "parse_env_database_url",
    "resolve_knowledge_schema",
    "resolve_knowledge_schema_for_connection",
    "validate_schema_name",
]
