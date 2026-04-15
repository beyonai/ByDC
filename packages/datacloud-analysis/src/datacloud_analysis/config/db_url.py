"""Helpers for reusing DATACLOUD_DB_* in datacloud-analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

_IGNORED_QUERY_KEYS = frozenset({"characterEncoding", "serverTimezone", "timeZone"})
_SCHEMA_QUERY_KEYS = ("currentSchema", "schema")


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


def _load_raw_database_url() -> str:
    raw_url = os.getenv("DATACLOUD_DB_URL", "").strip()
    if not raw_url:
        return ""
    if raw_url.startswith("jdbc:"):
        return raw_url[5:]
    return raw_url


def _build_netloc(user: str, password: str, host: str, port: int) -> str:
    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")
    auth = safe_user
    if password:
        auth = f"{safe_user}:{safe_password}"
    return f"{auth}@{host}:{port}"


def parse_env_database_url() -> ParsedDatabaseUrl | None:
    """Parse DATACLOUD_DB_* into a normalized connection target."""

    raw_database_url = _load_raw_database_url()
    if not raw_database_url:
        return None

    parsed = urlparse(raw_database_url)
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
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/") or "postgres",
        user=user,
        password=password,
        schema=schema,
        query_params=tuple(query_params),
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
    """Resolve checkpoint schema from DATACLOUD_DB_URL query params."""

    parsed = parse_env_database_url()
    if parsed is None:
        return default
    return parsed.schema or default
