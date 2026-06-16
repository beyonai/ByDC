"""FakeRegistry - in-memory OntologyBase registry for testing.

Mirrors OntologyBaseRegistry interface.
"""

from __future__ import annotations


class OntologyBaseEntry:
    """Test-compatible entry with same fields as registry/models.py."""

    def __init__(
        self,
        base_id: str,
        display_name: str,
        description: str = "",
        owner_type: str = "personal",
        source_type: str = "LOCAL",
        source_url: str | None = None,
        auth_type: str | None = None,
        auth_config: dict | None = None,
        timeout_sec: int = 30,
        ontology_path: str = "",
        created_at: str = "",
    ) -> None:
        self.base_id = base_id
        self.display_name = display_name
        self.description = description
        self.owner_type = owner_type
        self.source_type = source_type
        self.source_url = source_url
        self.auth_type = auth_type
        self.auth_config = auth_config
        self.timeout_sec = timeout_sec
        self.ontology_path = ontology_path
        self.created_at = created_at


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
