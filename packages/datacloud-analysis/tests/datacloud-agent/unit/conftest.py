"""Unit-test-level fixtures for tests/unit/unit/.

Rules for fixtures placed here:
- No real DB connections, no real network calls.
- All external services must be mocked / stubbed.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from datacloud_analysis.session.pg_opengauss import OpenGaussSaver


# ---------------------------------------------------------------------------
# OpenGaussSaver stub — provides the minimal PostgresSaver parent interface
# ---------------------------------------------------------------------------

class StubSaver(OpenGaussSaver):
    """Minimal parent-class stub for testing OpenGaussSaver in isolation.

    Provides only the methods that ``OpenGaussSaver`` calls on ``self``
    (i.e. the PostgresSaver parent-class surface).  No real DB connection
    is created.

    Usage::

        stub = StubSaver(mock_cursor)
        result = stub.get_tuple(config)
    """

    def __init__(self, mock_cur: MagicMock) -> None:
        self._cur = mock_cur

    @contextmanager  # type: ignore[override]
    def _cursor(self, *, pipeline: bool = False):  # type: ignore[override]
        yield self._cur

    def _load_checkpoint_tuple(self, value: dict) -> dict:  # type: ignore[override]
        """Pass-through: let tests assert on the raw assembled dict."""
        return value

    def _search_where(self, config, filter, before):  # type: ignore[override]
        """Return empty WHERE clause by default; override per-test if needed."""
        return ("", [])

    def _dump_blobs(self, *args):  # type: ignore[override]
        return []

    def _dump_writes(self, *args):  # type: ignore[override]
        return []


@pytest.fixture()
def mock_cursor() -> MagicMock:
    """A fresh MagicMock representing a psycopg cursor."""
    return MagicMock()


@pytest.fixture()
def stub_saver(mock_cursor: MagicMock) -> StubSaver:
    """StubSaver wired to ``mock_cursor``."""
    return StubSaver(mock_cursor)
