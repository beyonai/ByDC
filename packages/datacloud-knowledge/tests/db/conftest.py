"""Shared fixtures for whale_datacloud DDL integration tests."""

from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import pytest

_REPO_SRC = Path(__file__).resolve().parents[4] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

_DB_ENV = import_module("datacloud_test_support.db_env")
configure_test_database_env = _DB_ENV.configure_test_database_env
load_first_available_env_defaults = _DB_ENV.load_first_available_env_defaults
project_env_candidates = _DB_ENV.project_env_candidates


def _load_defaults() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    candidates = project_env_candidates(repo_root)
    load_first_available_env_defaults(candidates)


_load_defaults()
configure_test_database_env("test", require_complete=False)


@pytest.fixture(scope="session")
def package_root() -> Path:
    """Return package root directory for datacloud-knowledge-service."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def ddl_dir(package_root: Path) -> Path:
    """Return whale_datacloud DDL directory path."""
    return package_root / "db" / "ddl" / "whale_datacloud"


@pytest.fixture(scope="session")
def db_config() -> dict[str, str | int]:
    """Load required DB config from environment variables."""
    required_keys = ["DATACLOUD_DB_URL", "DATACLOUD_DB_USER"]
    missing = [key for key in required_keys if not os.getenv(key)]
    if missing:
        pytest.skip(f"db_integration: missing env vars: {', '.join(missing)}")

    parsed = urlparse(os.environ["DATACLOUD_DB_URL"].removeprefix("jdbc:"))
    schema = next(
        (
            value
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key in {"currentSchema", "schema"} and value
        ),
        "whale_datacloud",
    )
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": str(os.environ["DATACLOUD_DB_USER"]),
        "password": os.getenv("DATACLOUD_DB_PASSWORD", ""),
        "database": parsed.path.lstrip("/") or "postgres",
        "schema": schema,
    }
