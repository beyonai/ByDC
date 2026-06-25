"""OntologyStore — in-memory index cache with mtime detection and debounced flush.

Zero-dependency on any concrete EntityStore implementation.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from datacloud_platform.ports.entity_store import EntityStore

logger = logging.getLogger(__name__)


class CacheMode(str, Enum):
    """Cache-control mode for ontology read operations.

    Attributes:
        REALTIME: Check cache, refresh on storage version mismatch (default).
        STORE: Hit cache without version check; fall through to REALTIME on miss.
        FORCE: Bypass cache, always rebuild from storage.
    """

    REALTIME = "realtime"
    STORE = "store"
    FORCE = "force"


@dataclass
class CacheEntry:
    """Per-entity-type cache entry holding the lightweight index and flush state."""

    data: dict[str, dict[str, Any]]
    version: str
    dirty: bool = False
    flush_timer: threading.Timer | None = None


class OntologyStore:
    """In-memory index cache layered over an :class:`EntityStore`.

    Key behaviours:

    - ``get_index`` compares ``storage_version()`` against the cached version to
      detect external modifications (e.g. another worker wrote the index file).
    - ``update_index`` / ``remove_from_index`` mark the cache dirty and schedule
      a **1-second debounced flush** via ``threading.Timer``.
    - ``invalidate`` eagerly pops the cache and cancels any pending timer.

    Thread-safety: all mutations to ``_indices`` and ``CacheEntry`` fields are
    guarded by ``_index_lock``.
    """

    _DEBOUNCE_SECONDS: float = 1.0

    def __init__(self, entity_store: EntityStore) -> None:
        self._store: EntityStore = entity_store
        self._indices: dict[str, CacheEntry] = {}
        self._index_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_index(
        self,
        entity_type: str,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, dict[str, Any]]:
        """Return the cached index for *entity_type*, respecting *cache_mode*.

        - ``FORCE``: bypass cache, always rebuild from storage.
        - ``STORE``: hit cache without version check; on miss, fall through to REALTIME.
        - ``REALTIME`` (default): compare ``storage_version()``, refresh on mismatch.

        When the underlying store's ``load_index`` raises an exception (e.g. corrupted
        file), auto-rebuilds the index via ``entity_store.rebuild_index()``.
        """
        if cache_mode == CacheMode.FORCE:
            return self._load_index_force(entity_type)

        if cache_mode == CacheMode.STORE:
            entry = self._indices.get(entity_type)
            if entry is not None:
                return entry.data
            # miss → fall through to REALTIME behaviour

        # REALTIME: mtime-based version detection
        return self._load_index_realtime(entity_type)

    def _load_index_realtime(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """REALTIME load: version-checked cache hit or rebuild."""
        version = self._store.storage_version(entity_type)
        entry = self._indices.get(entity_type)
        if entry and entry.version == version:
            return entry.data
        data = self._load_index_data(entity_type)
        # Refresh version — _load_index_data may have rebuilt and saved, changing mtime
        version = self._store.storage_version(entity_type)
        with self._index_lock:
            self._indices[entity_type] = CacheEntry(data=data, version=version)
        return data

    def _load_index_force(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """FORCE load: bypass cache, rebuild from storage and update cache."""
        data = self._store.load_index(entity_type)
        version = self._store.storage_version(entity_type)
        with self._index_lock:
            self._indices[entity_type] = CacheEntry(data=data, version=version)
        return data

    def _load_index_data(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Load index data, auto-rebuilding on failure."""
        try:
            return self._store.load_index(entity_type)
        except Exception:
            logger.warning(
                "Failed to load index for %s, rebuilding from entity files",
                entity_type,
                exc_info=True,
            )
            data = self._store.rebuild_index(entity_type)
            self._store.save_index(entity_type, data)
            return data

    def update_index(self, entity_type: str, code: str, entry: dict[str, Any]) -> None:
        """Insert or update *code* → *entry* in the cached index and schedule flush."""
        with self._index_lock:
            idx = self._indices.get(entity_type)
            if idx is None:
                data = self._store.load_index(entity_type)
                version = self._store.storage_version(entity_type)
                idx = CacheEntry(data=data, version=version)
                self._indices[entity_type] = idx
            idx.data[code] = entry
            idx.dirty = True
        self._schedule_flush(entity_type)

    def remove_from_index(self, entity_type: str, code: str) -> None:
        """Remove *code* from the cached index and schedule flush (no-op if uncached)."""
        with self._index_lock:
            idx = self._indices.get(entity_type)
            if idx is None:
                return
            idx.data.pop(code, None)
            idx.dirty = True
        self._schedule_flush(entity_type)

    def invalidate(self, entity_type: str) -> None:
        """Force-remove the cached index for *entity_type* and cancel any pending flush."""
        with self._index_lock:
            entry = self._indices.pop(entity_type, None)
            if entry is not None and entry.flush_timer is not None:
                entry.flush_timer.cancel()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule_flush(self, entity_type: str) -> None:
        entry = self._indices.get(entity_type)
        if entry is None:
            return
        with self._index_lock:
            if entry.flush_timer is not None:
                entry.flush_timer.cancel()
            entry.flush_timer = threading.Timer(
                self._DEBOUNCE_SECONDS, lambda: self._do_flush(entity_type)
            )
            entry.flush_timer.start()

    def _do_flush(self, entity_type: str) -> None:
        with self._index_lock:
            entry = self._indices.get(entity_type)
            if entry is None or not entry.dirty:
                return
            self._store.save_index(entity_type, entry.data)
            entry.version = self._store.storage_version(entity_type)
            entry.dirty = False
