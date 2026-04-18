"""Helpers for reusing DATACLOUD_DB_* in datacloud-analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlunparse


@dataclass(frozen=True)
class ParsedDatabaseUrl:
    """Normalized database settings loaded from DATACLOUD_DB_* env vars."""

    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str | None
    query_params: tuple[tuple[str, str], ...]


def _has_split_database_env() -> bool:
    return all(
        _read_text_env(name)
        for name in ("DATACLOUD_DB_HOST", "DATACLOUD_DB_DATABASE", "DATACLOUD_DB_USER")
    )
    # Password is allowed to be empty for local/trust-auth deployments.


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


def parse_env_database_url() -> ParsedDatabaseUrl | None:
    """Parse split DATACLOUD_DB_* env vars into a normalized connection target."""

    if not _has_split_database_env():
        return None

    user = _read_text_env("DATACLOUD_DB_USER")
    password = _read_password_env()
    schema = _read_text_env("DATACLOUD_DB_SCHEMA") or None

    return ParsedDatabaseUrl(
        host=_read_text_env("DATACLOUD_DB_HOST"),
        port=_read_port_env(5432),
        database=_read_text_env("DATACLOUD_DB_DATABASE"),
        user=user,
        password=password,
        schema=schema,
        query_params=(),
    )


def build_postgres_connection_uri() -> str:
    """Build a libpq-compatible PostgreSQL URI from DATACLOUD_DB_* env vars."""

    parsed = parse_env_database_url()
    if parsed is None:
        return ""

    query = urlencode(parsed.query_params, doseq=True)
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


def resolve_checkpoint_schema(default: str = "public") -> str:
    """Resolve checkpoint schema from DATACLOUD_DB_SCHEMA."""

    parsed = parse_env_database_url()
    if parsed is None:
        return default
    return parsed.schema or default
