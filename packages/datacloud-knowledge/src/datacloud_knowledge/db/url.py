"""Utilities for normalizing DATACLOUD PostgreSQL/OpenGauss connection env vars."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


@dataclass(frozen=True)
class ParsedDatabaseUrl:
    """Normalized DATACLOUD database connection settings."""

    db_type: str
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str | None
    query_params: tuple[tuple[str, str], ...]


def _normalize_db_type(raw_scheme: str) -> str:
    scheme = raw_scheme.strip().lower()
    if scheme == "opengauss":
        return "opengauss"
    return "postgresql"


def _read_text_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _read_password_env() -> str:
    return os.getenv("DATACLOUD_DB_PASSWORD", "")


def _read_port_env(default: int) -> int:
    raw_port = os.getenv("DATACLOUD_DB_PORT", "").strip()
    if not raw_port:
        return default
    try:
        return int(raw_port)
    except ValueError:
        return default


def _build_netloc(user: str, password: str, host: str, port: int) -> str:
    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")
    auth = safe_user
    if password:
        auth = f"{safe_user}:{safe_password}"
    return f"{auth}@{host}:{port}"


def parse_env_database_url() -> ParsedDatabaseUrl:
    """Parse split DATACLOUD database env vars into a normalized connection target."""

    db_type = _normalize_db_type(_read_text_env("DATACLOUD_DB_TYPE") or "postgresql")
    user = _read_text_env("DATACLOUD_DB_USER") or "postgres"
    password = _read_password_env()
    schema = _read_text_env("DATACLOUD_DB_SCHEMA") or None

    return ParsedDatabaseUrl(
        db_type=db_type,
        host=_read_text_env("DATACLOUD_DB_HOST") or "localhost",
        port=_read_port_env(5432),
        database=_read_text_env("DATACLOUD_DB_DATABASE") or "postgres",
        user=user,
        password=password,
        schema=schema,
        query_params=(),
    )


def parse_database_url(db_url: str) -> ParsedDatabaseUrl:
    """Parse a PostgreSQL/OpenGauss connection URL.

    Supported forms include regular libpq URLs and JDBC-style URLs such as
    ``jdbc:opengauss://host:5432/postgres?currentSchema=tenant``.
    """

    normalized = db_url.strip()
    if normalized.startswith("jdbc:"):
        normalized = normalized.removeprefix("jdbc:")

    parsed = urlparse(normalized)
    db_type = _normalize_db_type(parsed.scheme)
    if not parsed.hostname:
        raise ValueError("Database URL must include a host")
    if not parsed.path or parsed.path == "/":
        raise ValueError("Database URL must include a database name")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    schema: str | None = None
    remaining_query: list[tuple[str, str]] = []
    for key, value in query_pairs:
        key_lower = key.lower()
        if key_lower in {"currentschema", "search_path", "schema"}:
            schema = value or None
        elif key_lower == "options" and "search_path=" in value:
            _, _, raw_schema = value.partition("search_path=")
            schema = raw_schema.strip() or None
        else:
            remaining_query.append((key, value))

    return ParsedDatabaseUrl(
        db_type=db_type,
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=parsed.username or "postgres",
        password=parsed.password or "",
        schema=validate_schema_name(schema) if schema else None,
        query_params=tuple(remaining_query),
    )


def infer_database_type_from_url() -> str:
    """Infer database type from DATACLOUD_DB_TYPE."""

    return parse_env_database_url().db_type


def validate_schema_name(schema: str) -> str:
    """Validate a schema identifier before it is used in SQL.

    Schema names are identifiers, not bind parameters. Keeping the accepted
    grammar intentionally narrow lets all SQL call sites quote safely without
    allowing punctuation, whitespace, or statement separators.
    """

    normalized = schema.strip()
    if not _SCHEMA_NAME_RE.fullmatch(normalized):
        raise ValueError(
            "Invalid DATACLOUD knowledge schema name. Use an identifier matching "
            "^[A-Za-z_][A-Za-z0-9_]{0,62}$"
        )
    return normalized


def resolve_knowledge_schema(schema: str | None = None) -> str:
    """Resolve the knowledge schema from an explicit value or DATACLOUD_DB_SCHEMA.

    No default schema is assumed. Callers must pass ``schema`` or set
    ``DATACLOUD_DB_SCHEMA`` so deployments cannot accidentally write to a
    business-specific historical schema.
    """

    resolved = schema or parse_env_database_url().schema
    if not resolved:
        raise RuntimeError(
            "Knowledge schema is required. Pass schema explicitly or set DATACLOUD_DB_SCHEMA."
        )
    return validate_schema_name(resolved)


def resolve_knowledge_schema_for_connection(
    *,
    schema: str | None = None,
    db_url: str | None = None,
) -> str:
    """Resolve schema from explicit input, DB URL query parameters, or env."""

    parsed_schema = parse_database_url(db_url).schema if db_url else None
    return resolve_knowledge_schema(schema or parsed_schema)


def _resolve_parsed_database(db_url: str | None = None) -> ParsedDatabaseUrl:
    return parse_database_url(db_url) if db_url else parse_env_database_url()


def build_sqlalchemy_database_config(
    driver: str,
    *,
    schema: str | None = None,
    db_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a SQLAlchemy URL and connect args from DATACLOUD DB env vars."""

    parsed = _resolve_parsed_database(db_url)
    resolved_schema = resolve_knowledge_schema(schema or parsed.schema)
    query = urlencode(parsed.query_params, doseq=True)
    url = urlunparse(
        (
            f"postgresql+{driver}",
            _build_netloc(parsed.user, parsed.password, parsed.host, parsed.port),
            f"/{quote(parsed.database, safe='')}",
            "",
            query,
            "",
        )
    )

    connect_args: dict[str, Any] = {}
    if resolved_schema:
        if driver == "asyncpg":
            connect_args["server_settings"] = {"search_path": resolved_schema}
        else:
            connect_args["options"] = f"-csearch_path={resolved_schema}"
    return url, connect_args


def build_postgres_connection_uri(
    *,
    schema: str | None = None,
    db_url: str | None = None,
) -> str:
    """Build a libpq-compatible PostgreSQL URI from DATACLOUD DB env vars."""

    parsed = _resolve_parsed_database(db_url)
    resolved_schema = resolve_knowledge_schema(schema or parsed.schema)
    query_params = list(parsed.query_params)
    query_params.append(("options", f"-csearch_path={resolved_schema}"))
    query = urlencode(query_params, doseq=True)
    return urlunparse(
        (
            "postgresql",
            _build_netloc(parsed.user, parsed.password, parsed.host, parsed.port),
            f"/{quote(parsed.database, safe='')}",
            "",
            query,
            "",
        )
    )
