"""OntologyBaseEntry — per-base backend configuration + OntologyBaseRegistry."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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
    """In-memory registry of OntologyBaseEntry instances with JSON file persistence.

    Library management is always local — never routed through Backends.
    """

    def __init__(self) -> None:
        self._entries: dict[str, OntologyBaseEntry] = {}

    # ── Core CRUD ──────────────────────────────────────────────────────────

    def register(self, entry: OntologyBaseEntry) -> None:
        """Register a new base entry.

        Raises:
            ValueError: If a base with the same base_id already exists.
        """
        if entry.base_id in self._entries:
            raise ValueError(f"OntologyBase '{entry.base_id}' already registered")
        self._entries[entry.base_id] = entry

    def get(self, base_id: str) -> OntologyBaseEntry | None:
        """Get an entry by base_id, or None if not found."""
        return self._entries.get(base_id)

    def list(self) -> list[OntologyBaseEntry]:
        """List all registered entries."""
        return list(self._entries.values())

    def unregister(self, base_id: str) -> None:
        """Remove an entry by base_id.

        Raises:
            KeyError: If the base_id is not registered.
        """
        if base_id not in self._entries:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        del self._entries[base_id]

    def exists(self, base_id: str) -> bool:
        """Return True if *base_id* is registered."""
        return base_id in self._entries

    def update(self, base_id: str, **fields: Any) -> OntologyBaseEntry:
        """Update fields of an existing entry in-place.

        Only provided keyword arguments are applied.  ``base_id`` itself is
        read-only and ignored if passed.

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
        return entry

    # ── Persistence ────────────────────────────────────────────────────────

    def persist(self, path: Path) -> None:
        """Write all entries to *path* as a JSON array.

        Creates parent directories as needed.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self._entries.values()]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Persisted %d ontology base(s) to %s", len(data), path)

    @classmethod
    def restore(cls, path: Path) -> "OntologyBaseRegistry":
        """Load entries from a JSON file previously written by :meth:`persist`.

        If the file does not exist or is unreadable, returns an empty registry.
        """
        registry = cls()
        if not path.exists():
            logger.debug("Registry file not found at %s — starting empty", path)
            return registry
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read registry file %s: %s", path, exc)
            return registry
        if not isinstance(raw, list):
            logger.warning(
                "Registry file %s is not a JSON array — starting empty", path
            )
            return registry
        for item in raw:
            try:
                entry = OntologyBaseEntry(**item)
                registry._entries[entry.base_id] = entry
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping invalid registry entry in %s: %s", path, exc)
        logger.info(
            "Restored %d ontology base(s) from %s", len(registry._entries), path
        )
        return registry


def _default_registry_path() -> Path:
    """Return the default persist path, respecting the env-var override."""
    env = os.environ.get("DATACLOUD_BASE_REGISTRY_PATH")
    if env:
        return Path(env)
    return Path(".datacloud/bases.json")
