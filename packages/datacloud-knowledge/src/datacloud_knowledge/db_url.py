"""向后兼容 shim — 请使用 datacloud_knowledge.db.url。"""

from datacloud_knowledge.db.url import *  # noqa: F403
from datacloud_knowledge.db.url import (
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

__all__ = [
    "ParsedDatabaseUrl",
    "build_postgres_connection_uri",
    "build_sqlalchemy_database_config",
    "infer_database_type_from_url",
    "parse_database_url",
    "parse_env_database_url",
    "resolve_knowledge_schema",
    "resolve_knowledge_schema_for_connection",
    "validate_schema_name",
]
