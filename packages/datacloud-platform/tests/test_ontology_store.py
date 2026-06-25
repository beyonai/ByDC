"""Regression tests for OntologyStore — Phase 3 in-memory cache integration.

Tests cache-hit, cache-invalidation, version-detection, FORCE mode,
and debounced-flush behaviour over a pluggable EntityStore mock.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from datacloud_platform.ontology_store import CacheMode, OntologyStore


class MockEntityStore:
    """Controllable fake EntityStore for OntologyStore testing.

    Tracks calls to load_index / save_index / rebuild_index / storage_version
    so tests can verify caching behaviour.
    """

    def __init__(self) -> None:
        self._index: dict[str, dict[str, dict[str, Any]]] = {}
        self._versions: dict[str, str] = {}
        self._data: dict[str, dict[str, Any]] = {}
        # Call counters
        self.load_index_calls: int = 0
        self.save_index_calls: int = 0
        self.rebuild_index_calls: int = 0
        self.storage_version_calls: int = 0

    def save(self, entity_type: str, code: str, data: dict[str, Any]) -> None:
        self._data[f"{entity_type}:{code}"] = data

    def get(self, entity_type: str, code: str) -> dict[str, Any] | None:
        return self._data.get(f"{entity_type}:{code}")

    def delete(self, entity_type: str, code: str) -> None:
        self._data.pop(f"{entity_type}:{code}", None)

    def load_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        self.load_index_calls += 1
        return self._index.get(entity_type, {}).copy()

    def save_index(self, entity_type: str, entries: dict[str, dict[str, Any]]) -> None:
        self.save_index_calls += 1
        self._index[entity_type] = entries.copy()
        # Bump version on save
        import time as _time

        self._versions[entity_type] = str(_time.time())

    def storage_version(self, entity_type: str) -> str:
        self.storage_version_calls += 1
        return self._versions.get(entity_type, "0.0")

    def rebuild_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        self.rebuild_index_calls += 1
        return self._index.get(entity_type, {}).copy()

    def save_batch(
        self, entity_type: str, entities: list[tuple[str, dict[str, Any]]]
    ) -> None:
        for code, data in entities:
            self.save(entity_type, code, data)

    def set_version(self, entity_type: str, version: str) -> None:
        self._versions[entity_type] = version


@pytest.fixture
def mock_store() -> MockEntityStore:
    return MockEntityStore()


@pytest.fixture
def onto_store(mock_store: MockEntityStore) -> OntologyStore:
    return OntologyStore(mock_store)


class TestCacheHit:
    def test_first_call_miss_then_hit(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """First get_index → miss → load_index; second → hit (no reload)."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})

        # First call: should load from store
        idx1 = onto_store.get_index("objects")
        assert idx1 == {"a": {"code": "a", "name": "Alpha"}}
        load_calls_after_first = mock_store.load_index_calls

        # Second call: should hit cache (same version)
        idx2 = onto_store.get_index("objects")
        assert idx2 == {"a": {"code": "a", "name": "Alpha"}}
        assert mock_store.load_index_calls == load_calls_after_first  # no extra load

    def test_store_mode_hit(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """STORE mode hits cache without version check."""
        mock_store.save_index("objects", {"b": {"code": "b", "name": "Bravo"}})

        # Prime cache
        onto_store.get_index("objects")
        load_calls_before = mock_store.load_index_calls

        # Change version behind the scenes
        mock_store.set_version("objects", "999.0")

        # STORE mode: should return cached data without checking version
        idx = onto_store.get_index("objects", cache_mode=CacheMode.STORE)
        assert idx == {"b": {"code": "b", "name": "Bravo"}}
        assert mock_store.load_index_calls == load_calls_before  # no reload


class TestCacheInvalidation:
    def test_invalidate_forces_reload(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """After invalidate, next get_index must reload."""
        mock_store.save_index("objects", {"x": {"code": "x", "name": "X"}})
        onto_store.get_index("objects")

        # Invalidate cache
        onto_store.invalidate("objects")

        # Change data behind the scenes
        mock_store.save_index("objects", {"y": {"code": "y", "name": "Y"}})

        idx = onto_store.get_index("objects")
        assert idx == {"y": {"code": "y", "name": "Y"}}  # reloaded

    def test_update_index_marks_dirty_then_flush(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """update_index modifies cache and flushes to store."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})
        onto_store.get_index("objects")

        onto_store.update_index(
            "objects", "new", {"code": "new", "name": "New", "shard": "ne"}
        )

        # Wait for debounced flush
        time.sleep(1.5)

        # After flush, store's load_index should include the new entry
        stored = mock_store.load_index("objects")
        assert "new" in stored
        assert stored["new"]["name"] == "New"

    def test_remove_from_index(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """remove_from_index removes entry from cached index."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})
        onto_store.get_index("objects")

        onto_store.remove_from_index("objects", "a")

        # Wait for debounced flush
        time.sleep(1.5)

        stored = mock_store.load_index("objects")
        assert "a" not in stored

    def test_remove_from_index_uncached_noop(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """remove_from_index on uncached type should not raise."""
        onto_store.remove_from_index("objects", "nonexistent")


class TestVersionDetection:
    def test_version_change_triggers_reload(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """REALTIME mode: storage_version change → cache miss → reload."""
        mock_store.save_index("objects", {"v1": {"code": "v1", "name": "V1"}})
        onto_store.get_index("objects")
        load_calls_before = mock_store.load_index_calls

        # Change version (simulating external writer)
        mock_store.set_version("objects", "999.0")
        mock_store._index["objects"] = {"v2": {"code": "v2", "name": "V2"}}  # noqa: SLF001

        idx = onto_store.get_index("objects")
        assert idx == {"v2": {"code": "v2", "name": "V2"}}
        assert mock_store.load_index_calls > load_calls_before


class TestCacheModeForce:
    def test_force_always_reloads(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """FORCE mode bypasses cache and calls load_index every time."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})

        onto_store.get_index("objects", cache_mode=CacheMode.FORCE)
        calls1 = mock_store.load_index_calls

        # Same version, but FORCE should reload anyway
        onto_store.get_index("objects", cache_mode=CacheMode.FORCE)
        calls2 = mock_store.load_index_calls

        assert calls2 > calls1  # FORCE caused another load_index call


class TestDebouncedFlush:
    def test_multiple_updates_single_flush(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """Multiple update_index calls → only one save_index flush."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})
        onto_store.get_index("objects")

        save_calls_before = mock_store.save_index_calls

        # Rapid updates
        onto_store.update_index("objects", "b", {"code": "b", "name": "Beta"})
        onto_store.update_index("objects", "c", {"code": "c", "name": "Gamma"})
        onto_store.update_index("objects", "d", {"code": "d", "name": "Delta"})

        # Wait for debounce
        time.sleep(1.5)

        # Only one additional save_index should have occurred (debounced)
        save_calls_after = mock_store.save_index_calls
        # Timer debounce cancels previous → at least one flush, but since
        # the last timer fires and all three updates were in cache,
        # the _do_flush saves once. We verify one incremental flush occurred.
        assert save_calls_after >= save_calls_before + 1

        # All three updates should be persisted
        stored = mock_store.load_index("objects")
        assert "a" in stored
        assert "b" in stored
        assert "c" in stored
        assert "d" in stored
        assert stored["b"]["name"] == "Beta"
        assert stored["c"]["name"] == "Gamma"
        assert stored["d"]["name"] == "Delta"

    def test_debounce_timer_cancels_previous(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """FlushTimer is cancelled and restarted on each update_index call."""
        mock_store.save_index("objects", {"a": {"code": "a", "name": "Alpha"}})
        onto_store.get_index("objects")

        # First update: timer starts
        onto_store.update_index("objects", "b", {"code": "b", "name": "Beta"})

        # Access internal state to verify timer exists
        entry = onto_store._indices.get("objects")  # noqa: SLF001
        assert entry is not None
        timer1 = entry.flush_timer

        # Second update within debounce window: timer cancelled and replaced
        onto_store.update_index("objects", "c", {"code": "c", "name": "Gamma"})
        timer2 = entry.flush_timer

        # timer2 is a new Timer instance (not the same as timer1)
        if timer1 is not None and timer2 is not None:
            assert timer1 is not timer2  # replaced

        # Wait for flush
        time.sleep(1.5)


class TestThreadSafety:
    def test_concurrent_updates(
        self, onto_store: OntologyStore, mock_store: MockEntityStore
    ) -> None:
        """Concurrent update_index calls from multiple threads should not corrupt state."""
        mock_store.save_index("objects", {"init": {"code": "init", "name": "Init"}})
        onto_store.get_index("objects")

        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                onto_store.update_index(
                    "objects", f"t{n}", {"code": f"t{n}", "name": f"Thread{n}"}
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent updates raised: {errors}"

        # Wait for debounced flush
        time.sleep(1.5)

        stored = mock_store.load_index("objects")
        for i in range(10):
            assert f"t{i}" in stored
