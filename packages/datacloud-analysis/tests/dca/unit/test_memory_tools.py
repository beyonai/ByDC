from __future__ import annotations

import sys
import types
from typing import Any

import pytest


def _install_memory_query_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    search_experiences: Any,
) -> None:
    query_module = types.ModuleType("datacloud_memory.query")
    query_module.search_experiences = search_experiences  # type: ignore[attr-defined]

    package_module = types.ModuleType("datacloud_memory")
    package_module.query = query_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "datacloud_memory", package_module)
    monkeypatch.setitem(sys.modules, "datacloud_memory.query", query_module)


@pytest.mark.asyncio
async def test_recall_memory_returns_empty_when_backend_returns_non_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.memory.tools import recall_memory

    async def _search_experiences(*, user_id: str, query: str, limit: int) -> object:
        del user_id, query, limit
        return {"id": "m1"}

    _install_memory_query_module(monkeypatch, search_experiences=_search_experiences)

    result = await recall_memory.ainvoke({"query": "q", "user_id": "u", "limit": 3})
    assert result == []


@pytest.mark.asyncio
async def test_recall_memory_filters_non_dict_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.memory.tools import recall_memory

    async def _search_experiences(*, user_id: str, query: str, limit: int) -> object:
        del user_id, query, limit
        return [{"id": "m1", "title": "good"}, "bad-item", 123]

    _install_memory_query_module(monkeypatch, search_experiences=_search_experiences)

    result = await recall_memory.ainvoke({"query": "q", "user_id": "u", "limit": 3})
    assert result == [{"id": "m1", "title": "good"}]
