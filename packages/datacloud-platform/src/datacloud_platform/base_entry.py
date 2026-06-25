"""OntologyBaseEntry — per-base backend configuration + OntologyBaseRegistry."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.ports.entity_store import EntityStore

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Snowflake ID generator
# ═══════════════════════════════════════════════════════════════════════════════

_SNOWFLAKE_LOCK = threading.Lock()
_SNOWFLAKE_LAST_MS = 0
_SNOWFLAKE_SEQ = 0
_SNOWFLAKE_MAX_SEQ = 0x3FFFFF  # 22 bits → 4 194 304 IDs per millisecond


def generate_snowflake() -> str:
    """Snowflake-style ID: 42-bit ms timestamp + 22-bit monotonic sequence.

    16-character lowercase hex, lexicographically time-sortable.
    Thread-safe — sequence advances within same millisecond, resets on new ms.
    """
    global _SNOWFLAKE_LAST_MS, _SNOWFLAKE_SEQ

    ms = int(time.time() * 1000)
    with _SNOWFLAKE_LOCK:
        if ms == _SNOWFLAKE_LAST_MS:
            _SNOWFLAKE_SEQ += 1
        else:
            _SNOWFLAKE_LAST_MS = ms
            _SNOWFLAKE_SEQ = 0

        seq = _SNOWFLAKE_SEQ
        if seq > _SNOWFLAKE_MAX_SEQ:
            # Sequence exhausted in this ms — busy-wait until next ms
            while ms == _SNOWFLAKE_LAST_MS:
                ms = int(time.time() * 1000)
            _SNOWFLAKE_LAST_MS = ms
            _SNOWFLAKE_SEQ = 0
            seq = 0

    return f"{(ms << 22) | seq:016x}"


# ═══════════════════════════════════════════════════════════════════════════════
# Base entry pattern for valid base_id
# ═══════════════════════════════════════════════════════════════════════════════

_BASE_ID_RE = r"^[a-z][a-z0-9_-]{0,15}$"


def validate_base_id(base_id: str) -> bool:
    """Check whether *base_id* matches the allowed pattern.

    Rules: lowercase letter first char, total 1-16 chars, only ``[a-z0-9_-]``.
    """
    import re

    return bool(re.match(_BASE_ID_RE, base_id))


# ═══════════════════════════════════════════════════════════════════════════════
# OntologyBaseEntry
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class OntologyBaseEntry:
    """Ontology base entry — each base independently declares its backend composition.

    Resolution: source_type (coarse preset) → preset overlay → manual_backends (fine-grained).
    """

    base_id: str
    display_name: str
    description: str = ""
    owner_type: str = "personal"
    source_url: str | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    timeout_sec: int = 30
    created_at: str = ""

    # ── Coarse-grained: pick from preset table (empty = skip preset layer) ──
    source_type: str = ""

    # ── Fine-grained: per-Backend impl name (empty = inherit from layer above) ──
    manual_backends: dict[str, str] = field(default_factory=dict)
    # Example: {"ontology": "remote-http", "execution": "none"}

    backend_config: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Example: {"ontology": {"source_url": "https://..."}, "knowledge": {"cache_ttl": 300}}


# ═══════════════════════════════════════════════════════════════════════════════
# OntologyBaseRegistry — with JSON file persistence
# ═══════════════════════════════════════════════════════════════════════════════


class OntologyBaseRegistry:
    """In-memory registry of OntologyBaseEntry instances backed by an EntityStore.

    Each ``register`` / ``unregister`` persists the base entry as a sharded JSON
    file and atomically updates the ``bases`` entity-type index.

    Library management is always local — never routed through Backends.
    """

    def __init__(self, entity_store: EntityStore | None = None) -> None:
        if entity_store is None:
            from datacloud_platform.adapters.json_entity_store import JsonEntityStore
            from datacloud_platform.platform_file_storage import _data_dir

            entity_store = JsonEntityStore(_data_dir())
        self._store = entity_store
        self._entries: dict[str, OntologyBaseEntry] = {}

    # ── Core CRUD ──────────────────────────────────────────────────────────

    def register(self, entry: OntologyBaseEntry) -> None:
        """Register a new base entry.

        Persists the entry via the EntityStore and rebuilds the ``bases`` index.

        Raises:
            ValueError: If a base with the same base_id already exists.
        """
        if entry.base_id in self._entries:
            raise ValueError(f"OntologyBase '{entry.base_id}' already registered")
        self._entries[entry.base_id] = entry
        self._store.save("bases", entry.base_id, asdict(entry))
        self._rebuild_index()

    def get(self, base_id: str) -> OntologyBaseEntry | None:
        """Get an entry by base_id, or None if not found."""
        return self._entries.get(base_id)

    def list(self) -> list[OntologyBaseEntry]:
        """List all registered entries."""
        return list(self._entries.values())

    def unregister(self, base_id: str) -> None:
        """Remove an entry by base_id.

        Deletes the entity file and rebuilds the ``bases`` index.

        Raises:
            KeyError: If the base_id is not registered.
        """
        if base_id not in self._entries:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        del self._entries[base_id]
        self._store.delete("bases", base_id)
        self._rebuild_index()

    def exists(self, base_id: str) -> bool:
        """Return True if *base_id* is registered."""
        return base_id in self._entries

    def update(self, base_id: str, **fields: Any) -> OntologyBaseEntry:
        """Update fields of an existing entry in-place.

        Only provided keyword arguments are applied.  ``base_id`` itself is
        read-only and ignored if passed.

        Persists the updated entry via the EntityStore and rebuilds the index.

        Returns the updated entry.

        Raises:
            KeyError: If the base_id is not registered.
        """
        if base_id not in self._entries:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        entry = self._entries[base_id]
        fields.pop("base_id", None)
        for k, v in fields.items():
            if v is not None and hasattr(entry, k):
                setattr(entry, k, v)
        self._store.save("bases", base_id, asdict(entry))
        self._rebuild_index()
        return entry

    # ── Persistence ────────────────────────────────────────────────────────

    def restore(self) -> None:
        """Load entries from the EntityStore ``bases`` index.

        Called once at startup to hydrate the in-memory registry from disk.
        Idempotent — clears and replaces current entries.
        """
        index = self._store.load_index("bases")
        self._entries.clear()
        for base_id, data in index.items():
            try:
                entry = OntologyBaseEntry(**data)
                self._entries[entry.base_id] = entry
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping invalid base entry '%s' in bases index: %s",
                    base_id,
                    exc,
                )
        logger.info("Restored %d ontology base(s) from EntityStore", len(self._entries))

    def _rebuild_index(self) -> None:
        """Persist the full in-memory registry as the ``bases`` entity-type index."""
        entries: dict[str, dict[str, Any]] = {
            base_id: asdict(entry) for base_id, entry in self._entries.items()
        }
        self._store.save_index("bases", entries)
