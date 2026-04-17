"""Utilities for normalizing DATACLOUD PostgreSQL/OpenGauss connection env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlunparse


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
    return os.getenv("DATACLOUD_DB_PASS", "")


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


def infer_database_type_from_url() -> str:
    """Infer database type from DATACLOUD_DB_TYPE."""

    return parse_env_database_url().db_type


def resolve_knowledge_schema(default: str = "whale_datacloud") -> str:
    """Resolve knowledge schema from DATACLOUD_DB_SCHEMA."""

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
