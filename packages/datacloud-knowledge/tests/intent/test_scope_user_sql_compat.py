# ruff: noqa: S101
from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any

import pytest


def _get_cache_module() -> Any:
    return import_module("datacloud_knowledge.intent.cache")


def _get_sql_engine_module() -> Any:
    return import_module("datacloud_knowledge.query.sql_engine")


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
def test_user_name_cache_query_uses_coalesce_for_scope_user_id() -> None:
    cache_module = _get_cache_module()
    user_name_cache = cache_module.UserNameCache
    fake_session = _FakeSession()

    cache = user_name_cache()
    cache.load("test-user", fake_session)

    assert "COALESCE((tn.search_scope->>'scope_user_id'), '') = :user_id" in fake_session.sql_text
    assert fake_session.params == {"user_id": "test-user"}


@pytest.mark.intent
def test_sql_engine_name_index_does_not_use_scope_user_id_is_null() -> None:
    sql_engine_module = _get_sql_engine_module()
    method_source = inspect.getsource(sql_engine_module.SQLKnowledgeGraphQuery._build_name_index)

    assert "scope_user_id' IS NULL" not in method_source
    assert "COALESCE((tn.search_scope->>'scope_user_id'), '') = ''" in method_source
