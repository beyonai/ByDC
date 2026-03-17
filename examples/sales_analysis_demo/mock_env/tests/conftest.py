"""mock_env tests shared fixtures and marker registration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _mock_env_root() -> Path:
    return Path(__file__).resolve().parent.parent


ROOT = _mock_env_root()
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "type1_schema: DDL schema tests")
    config.addinivalue_line("markers", "type2_data: structured data load tests")
    config.addinivalue_line("markers", "type3_api: API service tests")
    config.addinivalue_line("markers", "type4_knowledge: knowledge ingest tests")
    config.addinivalue_line("markers", "e2e: end-to-end smoke tests")
    config.addinivalue_line("markers", "integration: requires external services")


@pytest.fixture(scope="session")
def mock_env_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def ddl_sql_path(mock_env_root: Path) -> Path:
    return mock_env_root / "db" / "crm_demo" / "sql" / "DDL.sql"


@pytest.fixture(scope="session")
def resource_data_dir(mock_env_root: Path) -> Path:
    return mock_env_root / "resource" / "data" / "crm_demo"


@pytest.fixture(scope="session")
def resource_knowledge_dir(mock_env_root: Path) -> Path:
    return mock_env_root / "resource" / "knowledge" / "crm_demo"


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    return os.getenv("DATACLOUD_ENABLE_INTEGRATION_TESTS", "0") == "1"


@pytest.fixture(scope="session")
def database_dsn() -> str | None:
    return os.getenv("DATACLOUD_TEST_DATABASE_DSN")
