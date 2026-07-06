"""JSON-file-backed EntityStore implementation with sharding and atomic writes."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from datacloud_platform.platform_file_storage import atomic_write_json

logger = logging.getLogger(__name__)

_SHARD_LEN = 2
_INDEX_FILENAME = "_index.json"


class JsonEntityStore:
    """Sharded JSON-file storage for ontology entities.

    Directory layout::

        {base_path}/
          {entity_type}/
            _index.json
            {shard}/
              {code}.json

    All writes go through :func:`atomic_write_json` (temp-file + rename).
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    # ------------------------------------------------------------------
    # public API — matches EntityStore Protocol
    # ------------------------------------------------------------------

    def save(self, entity_type: str, code: str, data: dict[str, Any]) -> None:
        """Write a single entity file atomically.  Does **not** update the index."""
        file_path = _shard_path(self._base_path, entity_type, code)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(file_path, data)

    def get(self, entity_type: str, code: str) -> dict[str, Any] | None:
        """Read a single entity by code.  Returns ``None`` when not found."""
        file_path = _shard_path(self._base_path, entity_type, code)
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except FileNotFoundError:
            return None

    def delete(self, entity_type: str, code: str) -> None:
        """Delete an entity file (idempotent — no error if missing)."""
        file_path = _shard_path(self._base_path, entity_type, code)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass

    def load_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Load the lightweight index ``{code: {name, shard, …}}``.

        Returns an empty dict when the index file does not exist.
        Auto-rebuilds and persists the index when the file is corrupted.
        """
        index_path = _index_path(self._base_path, entity_type)
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning(
                "Index file %s is corrupt, rebuilding from entity files", index_path
            )
            rebuilt = self.rebuild_index(entity_type)
            self.save_index(entity_type, rebuilt)
            return rebuilt

    def save_index(self, entity_type: str, entries: dict[str, dict[str, Any]]) -> None:
        """Persist the full index atomically."""
        index_path = _index_path(self._base_path, entity_type)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(index_path, entries)

    def storage_version(self, entity_type: str) -> str:
        """Return ``os.stat(_index.json).st_mtime`` as a string.

        Falls back to ``"0.0"`` when the index file does not exist yet.
        """
        index_path = _index_path(self._base_path, entity_type)
        try:
            return str(os.stat(index_path).st_mtime)
        except FileNotFoundError:
            return "0.0"

    def rebuild_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Full-scan all entity files and rebuild (and persist) the index."""
        type_dir = self._base_path / entity_type
        if not type_dir.is_dir():
            return {}

        entries: dict[str, dict[str, Any]] = {}
        for item in type_dir.iterdir():
            if not item.is_dir() or item.name.startswith("_"):
                continue
            for entity_file in item.iterdir():
                if entity_file.suffix != ".json" or entity_file.name.startswith("_"):
                    continue
                try:
                    data: dict[str, Any] = json.loads(
                        entity_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    logger.warning(
                        "Skipping unreadable entity file %s", entity_file, exc_info=True
                    )
                    continue
                entry = _to_index_entry(data, entity_type)
                code = entry["code"]
                if code:
                    entries[code] = entry

        self.save_index(entity_type, entries)
        return entries

    def save_batch(
        self, entity_type: str, entities: list[tuple[str, dict[str, Any]]]
    ) -> None:
        """Write many entities, then persist the index **once** at the end."""
        index_entries: dict[str, dict[str, Any]] = {}
        for code, data in entities:
            self.save(entity_type, code, data)
            entry = _to_index_entry(data, entity_type)
            index_entries[code] = entry
        self.save_index(entity_type, index_entries)


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


def _shard_path(base_path: Path, entity_type: str, code: str) -> Path:
    shard = code[:2].lower()
    return base_path / entity_type / shard / f"{code}.json"


def _index_path(base_path: Path, entity_type: str) -> Path:
    return base_path / entity_type / _INDEX_FILENAME


def _to_index_entry(data: dict[str, Any], entity_type: str) -> dict[str, Any]:
    singular = entity_type.rstrip("s")
    code_key = f"{singular}_code"
    name_key = f"{singular}_name"
    # Fallback to camelCase keys produced by model_dump(by_alias=True)
    camel_code_key = singular + "Code"  # e.g. objectCode, viewCode
    camel_name_key = singular + "Name"  # e.g. objectName, viewName
    code: str = data.get(code_key) or data.get(camel_code_key, "") or ""
    name: str = data.get(name_key) or data.get(camel_name_key, "") or ""
    return {
        "code": code,
        "name": name,
        "shard": code[:2].lower(),
        "field_count": len(data.get("fields", data.get("properties", []))),
    }
