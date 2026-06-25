"""Regression tests for JsonEntityStore — Phase 2 CRUD + shard-index operations."""

from __future__ import annotations

from pathlib import Path

import pytest
from datacloud_platform.adapters.json_entity_store import JsonEntityStore


@pytest.fixture
def store(tmp_path: Path) -> JsonEntityStore:
    """Create a JsonEntityStore rooted in a temp directory."""
    return JsonEntityStore(tmp_path)


class TestSaveAndGet:
    def test_save_and_get(self, store: JsonEntityStore) -> None:
        """Save an entity then retrieve it."""
        store.save(
            "objects", "test_obj", {"object_code": "test_obj", "object_name": "Test"}
        )
        data = store.get("objects", "test_obj")
        assert data is not None
        assert data["object_code"] == "test_obj"
        assert data["object_name"] == "Test"

    def test_get_nonexistent_returns_none(self, store: JsonEntityStore) -> None:
        store.save(
            "objects", "test_obj", {"object_code": "test_obj", "object_name": "Test"}
        )
        result = store.get("objects", "nonexistent")
        assert result is None


class TestDelete:
    def test_delete_existing(self, store: JsonEntityStore) -> None:
        store.save(
            "objects", "test_obj", {"object_code": "test_obj", "object_name": "Test"}
        )
        store.delete("objects", "test_obj")
        assert store.get("objects", "test_obj") is None

    def test_delete_nonexistent_is_idempotent(self, store: JsonEntityStore) -> None:
        """Delete on missing entity should not raise."""
        store.delete("objects", "nonexistent")


class TestIndex:
    def test_load_save_index(self, store: JsonEntityStore) -> None:
        entries = {"test_obj": {"code": "test_obj", "name": "Test", "shard": "te"}}
        store.save_index("objects", entries)
        loaded = store.load_index("objects")
        assert loaded == entries

    def test_load_index_empty_on_missing(self, store: JsonEntityStore) -> None:
        """load_index returns {} when index file does not exist."""
        loaded = store.load_index("objects")
        assert loaded == {}

    def test_storage_version_changes_on_save(self, store: JsonEntityStore) -> None:
        v1 = store.storage_version("objects")
        store.save_index("objects", {"a": {"code": "a", "name": "A", "shard": "aa"}})
        v2 = store.storage_version("objects")
        assert v1 != v2  # file changed → version changed

    def test_storage_version_default(self, store: JsonEntityStore) -> None:
        """storage_version returns '0.0' when no index exists."""
        v = store.storage_version("nonexistent_type")
        assert v == "0.0"


class TestSaveBatch:
    def test_save_batch(self, store: JsonEntityStore) -> None:
        entities: list[tuple[str, dict[str, object]]] = [
            ("a", {"object_code": "a", "object_name": "Alpha"}),
            ("b", {"object_code": "b", "object_name": "Bravo"}),
        ]
        store.save_batch("objects", entities)
        assert store.get("objects", "a") is not None
        assert store.get("objects", "b") is not None
        # Index should be persisted
        idx = store.load_index("objects")
        assert "a" in idx
        assert "b" in idx

    def test_save_batch_empty(self, store: JsonEntityStore) -> None:
        store.save_batch("objects", [])
        idx = store.load_index("objects")
        assert idx == {}


class TestRebuildIndex:
    def test_rebuild_index(self, store: JsonEntityStore) -> None:
        store.save("objects", "a", {"object_code": "a", "object_name": "Alpha"})
        store.save("objects", "b", {"object_code": "b", "object_name": "Bravo"})
        # Delete the index file to force rebuild
        idx_path = store._base_path / "objects" / "_index.json"  # noqa: SLF001
        if idx_path.exists():
            idx_path.unlink()
        idx = store.rebuild_index("objects")
        assert "a" in idx
        assert "b" in idx
        assert idx["a"]["code"] == "a"
        assert idx["a"]["name"] == "Alpha"

    def test_rebuild_index_empty_dir(self, store: JsonEntityStore) -> None:
        idx = store.rebuild_index("objects")
        assert idx == {}


class TestSharding:
    def test_entity_path_is_sharded(self, store: JsonEntityStore) -> None:
        """Entity files are stored under {entity_type}/{shard}/{code}.json."""
        store.save("objects", "order", {"object_code": "order", "object_name": "Order"})
        shard_dir = store._base_path / "objects" / "or"  # noqa: SLF001
        entity_file = shard_dir / "order.json"
        assert entity_file.exists()

    def test_different_types_isolated(self, store: JsonEntityStore) -> None:
        store.save("objects", "a", {"object_code": "a", "object_name": "Object A"})
        store.save("views", "a", {"view_code": "a", "view_name": "View A"})
        obj_data = store.get("objects", "a")
        view_data = store.get("views", "a")
        assert obj_data is not None
        assert view_data is not None
        assert obj_data["object_code"] == "a"
        assert view_data["view_code"] == "a"
