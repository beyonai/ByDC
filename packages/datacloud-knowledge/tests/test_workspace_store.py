"""WorkspaceStore 单元测试 — 先红后绿。

测试 LocalFileWorkspaceStore（不依赖 Redis），以及 get_workspace_store 工厂函数。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from datacloud_knowledge.ingestion.workspace_store import (
    LocalFileWorkspaceStore,
    WorkspaceStore,
    get_workspace_store,
)

# ── LocalFileWorkspaceStore ────────────────────────────────────────────────────


@pytest.fixture()
def local_store(tmp_path: Path) -> LocalFileWorkspaceStore:
    os.environ["ONTOLOGY_WORKSPACE_DIR"] = str(tmp_path)
    store = LocalFileWorkspaceStore()
    yield store
    os.environ.pop("ONTOLOGY_WORKSPACE_DIR", None)


def test_local_store_load_missing_key(local_store: LocalFileWorkspaceStore) -> None:
    """不存在的 key 返回空 dict。"""
    result = local_store.load("nonexistent_key")
    assert result == {}


def test_local_store_save_and_load(local_store: LocalFileWorkspaceStore) -> None:
    """save 后 load 能取回相同数据。"""
    state: dict[str, Any] = {"entity_code": "by_test", "entity_name": "测试对象"}
    local_store.save("by_test", state)
    loaded = local_store.load("by_test")
    assert loaded == state


def test_local_store_save_merge_semantics(local_store: LocalFileWorkspaceStore) -> None:
    """多次 save 覆盖整个 state（非 merge，merge 由上层逻辑负责）。"""
    local_store.save("key1", {"a": 1})
    local_store.save("key1", {"b": 2})
    loaded = local_store.load("key1")
    assert loaded == {"b": 2}


def test_local_store_delete_existing(local_store: LocalFileWorkspaceStore) -> None:
    """delete 后 load 返回空 dict。"""
    local_store.save("del_key", {"x": 1})
    local_store.delete("del_key")
    assert local_store.load("del_key") == {}


def test_local_store_delete_nonexistent(local_store: LocalFileWorkspaceStore) -> None:
    """delete 不存在的 key 不抛异常。"""
    local_store.delete("ghost_key")  # 不应抛出


def test_local_store_key_with_special_chars(local_store: LocalFileWorkspaceStore) -> None:
    """key 含 / 和 : 时能正常存取（文件名安全转义）。"""
    key = "session/abc:by_test"
    state: dict[str, Any] = {"entity_code": "by_test"}
    local_store.save(key, state)
    assert local_store.load(key) == state


def test_local_store_unicode_content(local_store: LocalFileWorkspaceStore) -> None:
    """中文内容能正确存取（ensure_ascii=False）。"""
    state: dict[str, Any] = {"entity_name": "我的任务", "desc": "中文描述"}
    local_store.save("unicode_key", state)
    loaded = local_store.load("unicode_key")
    assert loaded["entity_name"] == "我的任务"


def test_local_store_is_workspace_store_subclass(local_store: LocalFileWorkspaceStore) -> None:
    """LocalFileWorkspaceStore 是 WorkspaceStore 的子类。"""
    assert isinstance(local_store, WorkspaceStore)


# ── get_workspace_store 工厂 ───────────────────────────────────────────────────


def test_get_workspace_store_local(tmp_path: Path) -> None:
    """ONTOLOGY_STORE=local 时返回 LocalFileWorkspaceStore。"""
    os.environ["ONTOLOGY_STORE"] = "local"
    os.environ["ONTOLOGY_WORKSPACE_DIR"] = str(tmp_path)
    try:
        store = get_workspace_store()
        assert isinstance(store, LocalFileWorkspaceStore)
    finally:
        os.environ.pop("ONTOLOGY_STORE", None)
        os.environ.pop("ONTOLOGY_WORKSPACE_DIR", None)


def test_get_workspace_store_default_is_redis() -> None:
    """未设置 ONTOLOGY_STORE 时默认返回 RedisWorkspaceStore（类型检查，不连接）。"""
    pytest.importorskip("redis", reason="redis 包未安装，跳过 RedisWorkspaceStore 测试")
    from datacloud_knowledge.ingestion.workspace_store import RedisWorkspaceStore

    os.environ.pop("ONTOLOGY_STORE", None)
    # 不实际连接 Redis，只检查类型
    store = get_workspace_store()
    assert isinstance(store, RedisWorkspaceStore)


def test_get_workspace_store_redis_explicit() -> None:
    """ONTOLOGY_STORE=redis 时返回 RedisWorkspaceStore。"""
    pytest.importorskip("redis", reason="redis 包未安装，跳过 RedisWorkspaceStore 测试")
    from datacloud_knowledge.ingestion.workspace_store import RedisWorkspaceStore

    os.environ["ONTOLOGY_STORE"] = "redis"
    try:
        store = get_workspace_store()
        assert isinstance(store, RedisWorkspaceStore)
    finally:
        os.environ.pop("ONTOLOGY_STORE", None)
