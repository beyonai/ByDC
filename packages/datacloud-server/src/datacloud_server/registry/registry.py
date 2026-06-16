"""OntologyBase registry - manages base registration, query, and lifecycle."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class OntologyBaseEntry:
    """OntologyBase entry.

    sourceType is auto-derived: sourceUrl present -> REMOTE, else LOCAL.
    """

    base_id: str
    display_name: str
    description: str
    owner_type: str  # personal / enterprise
    source_type: str  # LOCAL / REMOTE
    source_url: str | None = None
    auth_type: str | None = None
    auth_config: dict | None = None
    timeout_sec: int = 30
    ontology_path: str = ""
    created_at: str = ""


class OntologyBaseRegistry:
    """OntologyBase registry - in-memory implementation."""

    def __init__(self) -> None:
        self._entries: dict[str, OntologyBaseEntry] = {}
        self._lock = Lock()

    def list(self) -> list[OntologyBaseEntry]:
        with self._lock:
            return list(self._entries.values())

    def get(self, base_id: str) -> OntologyBaseEntry | None:
        with self._lock:
            return self._entries.get(base_id)

    def register(self, entry: OntologyBaseEntry) -> None:
        with self._lock:
            if entry.base_id in self._entries:
                raise ValueError(f"OntologyBase '{entry.base_id}' already exists")
            self._entries[entry.base_id] = entry

    def unregister(self, base_id: str) -> None:
        with self._lock:
            if base_id not in self._entries:
                raise KeyError(f"OntologyBase '{base_id}' not found")
            del self._entries[base_id]
