"""Utilities for normalizing DATACLOUD PostgreSQL/OpenGauss connection env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

_DEFAULT_DB_URL = "jdbc:postgresql://localhost:5432/postgres"
_IGNORED_QUERY_KEYS = frozenset({"characterEncoding", "serverTimezone", "timeZone"})
_SCHEMA_QUERY_KEYS = ("currentSchema", "schema")


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


def _load_raw_database_url() -> str:
    raw_url = os.getenv("DATACLOUD_DB_URL", "").strip()
    if not raw_url:
        return _DEFAULT_DB_URL
    if raw_url.startswith("jdbc:"):
        return raw_url[5:]
    return raw_url


def _infer_db_type_from_scheme(raw_scheme: str) -> str:
    scheme = raw_scheme.strip().lower()
    if scheme == "opengauss":
        return "opengauss"
    return "postgresql"


def _build_netloc(user: str, password: str, host: str, port: int) -> str:
    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")
    auth = safe_user
    if password:
        auth = f"{safe_user}:{safe_password}"
    return f"{auth}@{host}:{port}"


def parse_env_database_url() -> ParsedDatabaseUrl:
    """Parse DATACLOUD database env vars into a normalized connection target."""

    parsed = urlparse(_load_raw_database_url())
    db_type = _infer_db_type_from_scheme(parsed.scheme)
    raw_query = parse_qsl(parsed.query, keep_blank_values=True)

    schema: str | None = None
    query_params: list[tuple[str, str]] = []
    for key, value in raw_query:
        if key in _SCHEMA_QUERY_KEYS and value and schema is None:
            schema = value
            continue
        if key in _IGNORED_QUERY_KEYS:
            continue
        query_params.append((key, value))

    user = os.getenv("DATACLOUD_DB_USER", "").strip() or parsed.username or "postgres"
    password = os.getenv("DATACLOUD_DB_PASSWORD", "")
    if not password and parsed.password:
        password = parsed.password

    return ParsedDatabaseUrl(
        db_type=db_type,
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/") or "postgres",
        user=user,
        password=password,
        schema=schema,
        query_params=tuple(query_params),
    )


def infer_database_type_from_url() -> str:
    """Infer database type from DATACLOUD_DB_URL."""

    return parse_env_database_url().db_type


def resolve_knowledge_schema(default: str = "whale_datacloud") -> str:
    """Resolve knowledge schema from DATACLOUD_DB_URL query params."""

    return parse_env_database_url().schema or default


def build_sqlalchemy_database_config(driver: str) -> tuple[str, dict[str, Any]]:
    """Build a SQLAlchemy URL and connect args from DATACLOUD DB env vars."""

    parsed = parse_env_database_url()
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
    if parsed.schema:
        if driver == "asyncpg":
            connect_args["server_settings"] = {"search_path": parsed.schema}
        else:
            connect_args["options"] = f"-csearch_path={parsed.schema}"
    return url, connect_args


def build_postgres_connection_uri() -> str:
    """Build a libpq-compatible PostgreSQL URI from DATACLOUD DB env vars."""

    parsed = parse_env_database_url()
    query_params = list(parsed.query_params)
    if parsed.schema:
        query_params.append(("options", f"-csearch_path={parsed.schema}"))
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
