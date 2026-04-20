"""Pytest configuration for intent unit tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "intent: intent subpackage tests")
    config.addinivalue_line("markers", "db_integration: requires reachable database (skipped)")
