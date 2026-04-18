from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_SRC = _REPO_ROOT / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

_DB_ENV = import_module("datacloud_test_support.db_env")
_DB_ENV.load_first_available_env_defaults(_DB_ENV.project_env_candidates(_REPO_ROOT))
_DB_ENV.configure_test_database_env("test", require_complete=False)

_KB_SRC = _REPO_ROOT / "packages" / "datacloud-knowledge" / "src"
if str(_KB_SRC) not in sys.path:
    sys.path.insert(0, str(_KB_SRC))

_REQUIRED_DB_ENV_VARS = (
    "DATACLOUD_DB_HOST",
    "DATACLOUD_DB_DATABASE",
    "DATACLOUD_DB_USER",
    "DATACLOUD_DB_PASSWORD",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "intent: intent subpackage tests")
    config.addinivalue_line("markers", "integration: requires external services")
    config.addinivalue_line(
        "markers", "db_integration: requires reachable PostgreSQL/openGauss database"
    )


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    return os.getenv("DATACLOUD_ENABLE_INTEGRATION_TESTS", "0") == "1"


@pytest.fixture
def db_session(integration_enabled: bool) -> Iterator[Session]:
    if not any(os.getenv(name, "").strip() for name in _REQUIRED_DB_ENV_VARS):
        pytest.skip(
            "Missing DB env vars: DATACLOUD_DB_HOST / DATACLOUD_DB_DATABASE / "
            "DATACLOUD_DB_USER / DATACLOUD_DB_PASSWORD"
        )

    if not integration_enabled:
        pytest.skip("DATACLOUD_ENABLE_INTEGRATION_TESTS is not enabled")

    connection_module = import_module("datacloud_knowledge.knowledge_search.db.connection")
    get_session = connection_module.get_session

    with get_session() as session:
        try:
            yield session
        finally:
            session.rollback()
