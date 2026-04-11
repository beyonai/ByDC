"""Shared fixtures for whale_datacloud DDL integration tests."""

from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path

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
    required_keys = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [key for key in required_keys if not os.getenv(key)]
    if missing:
        pytest.skip(f"db_integration: missing env vars: {', '.join(missing)}")

    schema = os.getenv("DB_SCHEMA", "whale_datacloud")
    return {
        "host": str(os.environ["DB_HOST"]),
        "port": int(os.environ["DB_PORT"]),
        "user": str(os.environ["DB_USER"]),
        "password": str(os.environ["DB_PASSWORD"]),
        "database": str(os.environ["DB_NAME"]),
        "schema": schema,
    }
