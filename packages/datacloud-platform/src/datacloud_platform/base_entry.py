"""OntologyBaseEntry — per-base backend configuration + OntologyBaseRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


class OntologyBaseRegistry:
    """In-memory registry of OntologyBaseEntry instances.

    Library management is always local — never routed through Backends.
    """

    def __init__(self) -> None:
        self._entries: dict[str, OntologyBaseEntry] = {}

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
