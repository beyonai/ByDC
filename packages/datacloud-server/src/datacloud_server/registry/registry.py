"""OntologyBase registry - manages base registration, query, and lifecycle."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
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
    """OntologyBase registry - in-memory with optional JSON disk persistence."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._entries: dict[str, OntologyBaseEntry] = {}
        self._lock = Lock()
        self._persist_path = persist_path
        if self._persist_path is not None:
            self._load_from_disk()

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
            self._persist_locked()

    def unregister(self, base_id: str) -> None:
        with self._lock:
            if base_id not in self._entries:
                raise KeyError(f"OntologyBase '{base_id}' not found")
            del self._entries[base_id]
            self._persist_locked()

    # ── disk persistence ────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        """Load entries from the JSON persist file.

        On any error (missing file, invalid JSON), logs a warning and starts
        with an empty registry.
        """
        path_str = self._persist_path
        if path_str is None:
            return  # not called with None, but guard for type safety
        path = Path(path_str)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # First-time start — no file to load, that's fine.
            return
        try:
            data: dict = json.loads(raw)
        except Exception:
            logger.warning(
                "Failed to parse registry persist file %r; starting empty.",
                path_str,
            )
            return
        for base_id, fields in data.items():
            self._entries[base_id] = OntologyBaseEntry(**fields)

    def _persist_locked(self) -> None:
        """Write the current registry state to disk atomically.

        Called *inside* the lock — serialises self._entries to JSON, writes
        to a temporary file, then does an atomic os.replace to swap it in.
        """
        if self._persist_path is None:
            return
        data = {bid: asdict(e) for bid, e in self._entries.items()}
        target = Path(self._persist_path)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(target)
