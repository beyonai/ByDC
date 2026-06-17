"""FakeRegistry - in-memory OntologyBase registry for testing.

Mirrors OntologyBaseRegistry interface.
"""

from __future__ import annotations

from datacloud_server.registry.registry import OntologyBaseEntry


class FakeRegistry:
    """In-memory registry - same interface as OntologyBaseRegistry."""

    def __init__(self, entries: list[OntologyBaseEntry] | None = None) -> None:
        self._entries: dict[str, OntologyBaseEntry] = {}
        for e in entries or []:
            self._entries[e.base_id] = e

    def list(self) -> list[OntologyBaseEntry]:
        return list(self._entries.values())

    def get(self, base_id: str) -> OntologyBaseEntry | None:
        return self._entries.get(base_id)

    def register(self, entry: OntologyBaseEntry) -> None:
        if entry.base_id in self._entries:
            raise ValueError(f"OntologyBase '{entry.base_id}' already exists")
        self._entries[entry.base_id] = entry

    def unregister(self, base_id: str) -> None:
        if base_id not in self._entries:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        del self._entries[base_id]
