from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from dotenv import load_dotenv

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_TEST = _REPO_ROOT / ".vscode" / ".env.test"
if _ENV_TEST.exists():
    load_dotenv(_ENV_TEST, override=True)

# OpenGauss compatibility: set KNOWLEDGE_DB_TYPE so the connection module
# applies the PGDialect version patch before creating the engine.
if not os.getenv("KNOWLEDGE_DB_TYPE"):
    os.environ["KNOWLEDGE_DB_TYPE"] = "opengauss"

_KB_SRC = _REPO_ROOT / "packages" / "datacloud-knowledge" / "src"
if str(_KB_SRC) not in sys.path:
    sys.path.insert(0, str(_KB_SRC))

_REQUIRED_DB_ENV_VARS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


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
    missing = [name for name in _REQUIRED_DB_ENV_VARS if not os.getenv(name)]
    if missing:
        pytest.skip(f"Missing DB env vars: {', '.join(missing)}")

    if not integration_enabled:
        pytest.skip("DATACLOUD_ENABLE_INTEGRATION_TESTS is not enabled")

    connection_module = import_module("datacloud_knowledge.knowledge_search.db.connection")
    get_session = connection_module.get_session

    with get_session() as session:
        try:
            yield session
        finally:
            session.rollback()
