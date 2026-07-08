"""JSON-file-backed EntityStore implementation with sharding, atomic writes, and version-based
cache invalidation.

警告：本实现依赖本地文件锁和 _version.json 版本管理，
仅支持单机部署。多机部署请使用 OpenGaussEntityStore。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from datacloud_platform.platform_file_storage import atomic_write_json
from datacloud_platform.ports.entity_store import EntityStore

logger = logging.getLogger(__name__)

_SHARD_LEN = 2
_INDEX_FILENAME = "_index.json"
_VERSION_FILENAME = "_version.json"

_version_lock = threading.Lock()
"""Per-process lock for _version.json reads and bumps."""


class _ScopedEntityStore:
    """Lightweight proxy — only overrides ``base_id`` default; delegates everything else.

    Two-slot zero-overhead wrapper.  Shared by both JsonEntityStore and
    OpenGaussEntityStore via :meth:`EntityStore.sub_store`.
    """

    __slots__ = ("_parent", "_default_base_id")

    def __init__(self, parent: EntityStore, *, default_base_id: str) -> None:
        self._parent = parent
        self._default_base_id = default_base_id

    # ── EntityStore Protocol (forward with overridden base_id) ───────────

    def save(
        self,
        entity_type: str,
        code: str,
        data: dict[str, Any],
        *,
        base_id: str = "",
    ) -> None:
        self._parent.save(
            entity_type, code, data, base_id=base_id or self._default_base_id
        )

    def get(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        return self._parent.get(
            entity_type, code, base_id=base_id or self._default_base_id
        )

    def delete(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> None:
        self._parent.delete(entity_type, code, base_id=base_id or self._default_base_id)

    def load_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        return self._parent.load_index(
            entity_type, base_id=base_id or self._default_base_id
        )

    def save_index(
        self,
        entity_type: str,
        entries: dict[str, dict[str, Any]],
        *,
        base_id: str = "",
    ) -> None:
        self._parent.save_index(
            entity_type, entries, base_id=base_id or self._default_base_id
        )

    def storage_version(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> str:
        return self._parent.storage_version(
            entity_type, base_id=base_id or self._default_base_id
        )

    def rebuild_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        return self._parent.rebuild_index(
            entity_type, base_id=base_id or self._default_base_id
        )

    def save_batch(
        self,
        entity_type: str,
        entities: list[tuple[str, dict[str, Any]]],
        *,
        base_id: str = "",
    ) -> None:
        self._parent.save_batch(
            entity_type, entities, base_id=base_id or self._default_base_id
        )

    def sub_store(self, namespace: str) -> _ScopedEntityStore:
        return _ScopedEntityStore(self._parent, default_base_id=namespace)


class JsonEntityStore:
    """Sharded JSON-file storage for ontology entities.

    Directory layout::

        {base_path}/
          {entity_type}/
            _index.json
            _version.json
            {shard}/
              {code}.json

    All writes go through :func:`atomic_write_json` (temp-file + rename).

    警告：本实现依赖本地文件锁和 _version.json 版本管理，
    仅支持单机部署。多机部署请使用 OpenGaussEntityStore。
    """

    def __init__(self, base_path: Path, *, default_base_id: str = "") -> None:
        self._base_path = base_path
        self._default_base_id = default_base_id

    # ── EntityStore Protocol ────────────────────────────────────────────

    def save(
        self,
        entity_type: str,
        code: str,
        data: dict[str, Any],
        *,
        base_id: str = "",
    ) -> None:
        """Write a single entity file and update the index atomically, then bump version."""
        _ = base_id
        file_path = _shard_path(self._base_path, entity_type, code)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(file_path, data)
        self._upsert_index_entry(entity_type, code, data)
        self._bump_version(entity_type)

    def get(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Read a single entity by code.  Returns ``None`` when not found."""
        _ = base_id
        file_path = _shard_path(self._base_path, entity_type, code)
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except FileNotFoundError:
            return None

    def delete(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> None:
        """Delete an entity file and remove from index (idempotent), then bump version."""
        _ = base_id
        file_path = _shard_path(self._base_path, entity_type, code)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass
        self._remove_index_entry(entity_type, code)
        self._bump_version(entity_type)

    def load_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Load the lightweight index, stripping internal ``shard`` keys.

        Auto-rebuilds and persists the index when the file is corrupted.
        Returns backend-independent entries: ``{code: {code, name}}``.
        """
        _ = base_id
        index_path = _index_path(self._base_path, entity_type)
        try:
            raw: dict[str, dict[str, Any]] = json.loads(
                index_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning(
                "Index file %s is corrupt, rebuilding from entity files", index_path
            )
            raw = self.rebuild_index(entity_type)

        return {
            code: {"code": entry["code"], "name": entry.get("name", code)}
            for code, entry in raw.items()
        }

    def save_index(
        self,
        entity_type: str,
        entries: dict[str, dict[str, Any]],
        *,
        base_id: str = "",
    ) -> None:
        """Persist the full index atomically, then bump version."""
        _ = base_id
        index_path = _index_path(self._base_path, entity_type)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(index_path, entries)
        self._bump_version(entity_type)

    def storage_version(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> str:
        """Return the version counter from ``_version.json``.

        Monotonic counter — increments on every save / delete / save_index.
        Consumers compare via ``==``; the value is opaque.
        """
        _ = base_id
        path = _version_path(self._base_path, entity_type)
        try:
            return str(json.loads(path.read_text(encoding="utf-8"))["version"])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return "0"

    def rebuild_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Full-scan all entity files, rebuild and persist the index.  Bumps version."""
        _ = base_id
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
        # return backend-independent format
        return {
            code: {"code": entry["code"], "name": entry.get("name", code)}
            for code, entry in entries.items()
        }

    def save_batch(
        self,
        entity_type: str,
        entities: list[tuple[str, dict[str, Any]]],
        *,
        base_id: str = "",
    ) -> None:
        """Write many entities, then rebuild index + bump version ONCE."""
        _ = base_id
        # Write individual entity files (no bump per entity)
        for code, data in entities:
            self._save_one(entity_type, code, data)

        # Rebuild index from current disk state (captures the batch)
        index_entries = self._rebuild_index_raw(entity_type)
        self.save_index(entity_type, index_entries)  # bumps version internally

    def sub_store(self, namespace: str) -> _ScopedEntityStore:
        """Return a lightweight scoped view with *namespace* as default base_id."""
        return _ScopedEntityStore(self, default_base_id=namespace)

    # ── Internal helpers ────────────────────────────────────────────────

    def _save_one(self, entity_type: str, code: str, data: dict[str, Any]) -> None:
        """Write a single entity WITHOUT bumping version (for batch use)."""
        file_path = _shard_path(self._base_path, entity_type, code)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(file_path, data)

    def _rebuild_index_raw(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Full-scan and return raw index entries (WITH internal fields like shard)."""
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
        return entries

    def _upsert_index_entry(
        self, entity_type: str, code: str, data: dict[str, Any]
    ) -> None:
        """Add or update a single entry in ``_index.json`` WITHOUT bumping version.

        Called by :meth:`save` to keep the index consistent with the shard file.
        """
        index_path = _index_path(self._base_path, entity_type)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw: dict[str, dict[str, Any]] = json.loads(
                index_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        raw[code] = _to_index_entry(data, entity_type)
        atomic_write_json(index_path, raw)

    def _remove_index_entry(self, entity_type: str, code: str) -> None:
        """Remove a single entry from ``_index.json`` WITHOUT bumping version.

        Called by :meth:`delete` to keep the index consistent with the shard file.
        """
        index_path = _index_path(self._base_path, entity_type)
        try:
            raw: dict[str, dict[str, Any]] = json.loads(
                index_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if code in raw:
            del raw[code]
            atomic_write_json(index_path, raw)

    def _bump_version(self, entity_type: str) -> None:
        """Atomically increment the version counter for *entity_type*."""
        path = _version_path(self._base_path, entity_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _version_lock:
            try:
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                v: int = int(data.get("version", 0)) + 1
            except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
                v = 1
            atomic_write_json(path, {"version": v})


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _shard_path(base_path: Path, entity_type: str, code: str) -> Path:
    shard = code[:2].lower()
    return base_path / entity_type / shard / f"{code}.json"


def _index_path(base_path: Path, entity_type: str) -> Path:
    return base_path / entity_type / _INDEX_FILENAME


def _version_path(base_path: Path, entity_type: str) -> Path:
    return base_path / entity_type / _VERSION_FILENAME


def _to_index_entry(data: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Extract index metadata from raw entity data.

    Returns internal index format (MAY include ``shard`` and other internal
    fields).  ``load_index()`` strips the internal fields before returning
    to callers — see the Protocol contract.
    """
    singular = entity_type.rstrip("s")
    code_key = f"{singular}_code"
    name_key = f"{singular}_name"
    camel_code_key = singular + "Code"
    camel_name_key = singular + "Name"
    id_key = f"{singular}_id"  # fallback: some entities use _id instead of _code
    code: str = (
        data.get(code_key) or data.get(camel_code_key, "") or data.get(id_key, "") or ""
    )
    name: str = data.get(name_key) or data.get(camel_name_key, "") or ""
    return {
        "code": code,
        "name": name,
        "shard": code[:2].lower(),
        "field_count": len(data.get("fields", data.get("properties", []))),
    }
