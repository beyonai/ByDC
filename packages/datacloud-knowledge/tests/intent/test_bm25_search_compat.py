from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _get_bm25_module() -> Any:
    return import_module("datacloud_knowledge.search.bm25")


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _NoTsvColumnSession:
    def __init__(self) -> None:
        self.seen_sql: list[str] = []

    def execute(self, stmt: Any, _params: dict[str, Any]) -> _FakeResult:
        sql_text = str(stmt)
        self.seen_sql.append(sql_text)

        if "information_schema.columns" in sql_text:
            return _FakeResult([])

        raise AssertionError("bm25 query should fail-fast before running search SQL")

    def rollback(self) -> None:
        return


class _QueryFailingSession:
    def __init__(self) -> None:
        self.rollback_called = False

    def execute(self, stmt: Any, _params: dict[str, Any]) -> _FakeResult:
        sql_text = str(stmt)
        if "information_schema.columns" in sql_text:
            return _FakeResult([(1,)])
        raise RuntimeError("boom")

    def rollback(self) -> None:
        self.rollback_called = True


@pytest.fixture(autouse=True)
def _reset_name_keywords_cache() -> None:
    bm25_module = _get_bm25_module()
    bm25_module._COLUMN_CAPS_CACHE["name_keywords"] = None


@pytest.mark.intent
def test_bm25_search_raises_when_name_keywords_column_missing() -> None:
    bm25_module = _get_bm25_module()
    bm25_search = bm25_module.bm25_search
    session = _NoTsvColumnSession()

    with pytest.raises(RuntimeError, match="name_keywords"):
        bm25_search(session, "企业综合分析表", top_k=5, min_score=0.1)


@pytest.mark.intent
def test_bm25_search_rolls_back_session_on_error() -> None:
    bm25_module = _get_bm25_module()
    bm25_search = bm25_module.bm25_search
    session = _QueryFailingSession()

    with pytest.raises(RuntimeError, match="boom"):
        bm25_search(session, "浼佷笟", top_k=3)

    assert session.rollback_called is True
