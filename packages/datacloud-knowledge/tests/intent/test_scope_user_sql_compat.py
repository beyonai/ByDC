from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _get_cache_module() -> Any:
    return import_module("datacloud_knowledge.intent.cache")


class _FakeResult:
    def fetchall(self) -> list[tuple[Any, ...]]:
        return []


class _FakeSession:
    def __init__(self) -> None:
        self.sql_text = ""
        self.params: dict[str, Any] = {}

    def execute(self, stmt: Any, params: dict[str, Any]) -> _FakeResult:
        self.sql_text = str(stmt)
        self.params = params
        return _FakeResult()


@pytest.mark.intent
def test_user_name_cache_query_uses_scope_user_id_filter() -> None:
    cache_module = _get_cache_module()
    user_name_cache = cache_module.UserNameCache
    fake_session = _FakeSession()

    cache = user_name_cache()
    cache.load("test-user", fake_session)

    assert "tn.search_scope->>'scope_user_id' = :user_id" in fake_session.sql_text
    assert fake_session.params == {"user_id": "test-user"}
