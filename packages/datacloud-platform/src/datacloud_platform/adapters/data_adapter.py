"""DataCloudDataBackend — OntologyBackend + StorageBackend via datacloud-data SDK."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.models import ObjectSummary, ParsedOwlContent, StoredFile

logger = logging.getLogger(__name__)

_STORAGE_DIR_ENV = "DATACLOUD_STORAGE_DIR"
_DEFAULT_STORAGE_DIR = ".datacloud_results"


class DataCloudDataBackend:
    """OntologyBackend + StorageBackend via datacloud-data SDK.

    Each method imports the concrete SDK class locally so the package
    does not hard-depend on datacloud-data at import time.
    """

    # ── OntologyBackend ────────────────────────────────────────────────────

    def parse_owl(self, directory: Path) -> ParsedOwlContent:
        """Parse OWL directory via OwlParser, return typed ParsedOwlContent.

        Args:
            directory: Path to the OWL resource directory.

        Returns:
            ParsedOwlContent with objects, views, relations lists.
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser  # noqa: PLC0415

        raw: dict[str, Any] = OwlParser().parse_resource_directory(directory)
        return ParsedOwlContent(
            objects=list(raw.get("objects", [])),
            views=list(raw.get("views", [])),
            relations=list(raw.get("relations", [])),
        )

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into a queryable runtime object.

        Args:
            base_path: Path to the OWL resource directory root.

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        loader = OntologyLoader()
        if base_path.exists():
            loader.load_from_owl_resource_directory(str(base_path))
        return loader  # type: ignore[return-value]

    def load_terms(
        self, _loader: OntologyQueryable, *, library_id: str = "PERSONAL_LIB"
    ) -> Any:
        """Load term index from knowledge DB via TermLoader.

        Uses the datacloud_data_sdk reference TermLoader implementation.
        The return type is intentionally ``Any``: TermLoader is not yet
        abstracted into a Protocol.

        Args:
            loader: An OntologyQueryable (typically an OntologyLoader).
            library_id: Library identifier (default ``PERSONAL_LIB``).

        Returns:
            A TermLoader instance.
        """
        from datacloud_data_sdk.ontology.term_loader import TermLoader  # noqa: PLC0415

        _ = library_id  # consumed by concrete TermLoader subclass
        return TermLoader()  # type: ignore[abstract]

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Create physical table for DYNAMIC_TABLE objects.

        Args:
            object_code: Ontology object code / table name.
            fields: Column definitions.
        """
        from datacloud_data_sdk.ddl.table_manager import (  # noqa: PLC0415
            create_table as _create_table,
        )

        _create_table(object_code, fields)

    def drop_table(self, object_code: str) -> None:
        """Drop physical table.

        Args:
            object_code: Ontology object code / table name.
        """
        from datacloud_data_sdk.ddl.table_manager import drop_table as _drop_table  # noqa: PLC0415

        _drop_table(object_code)

    def get_objects(
        self, loader: OntologyQueryable, base_id: str, scene_id: str
    ) -> list[ObjectSummary]:
        """Get all object summaries under a scene.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.
            scene_id: Scene / namespace identifier.

        Returns:
            List of ObjectSummary for every class in the loader.
        """
        _ = base_id, scene_id
        return [self._to_summary(cls) for cls in loader._classes.values()]

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> ObjectSummary | None:
        """Get single object detail by code.

        Args:
            loader: An OntologyQueryable with _classes populated.
            object_code: The object code to look up.

        Returns:
            ObjectSummary if found, otherwise None.
        """
        cls = loader._classes.get(object_code)
        if cls is None:
            return None
        return self._to_summary(cls)

    # ── Object CRUD (stub — datacloud-data SDK does not yet support) ────────

    def create_object(self, base_id: str, scene_id: str, obj: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object creation not supported via datacloud-data SDK")

    def update_object(
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object update not supported via datacloud-data SDK")

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object deletion not supported via datacloud-data SDK")

    # ── View CRUD (stub — datacloud-data SDK does not yet support) ──────────

    def get_views(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Return empty list — views not yet available via SDK."""
        return []

    def get_view_detail(
        self, base_id: str, scene_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Return None — view details not yet available via SDK."""
        return None

    def create_view(self, base_id: str, scene_id: str, view: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View creation not supported via datacloud-data SDK")

    def update_view(
        self, base_id: str, scene_id: str, view_code: str, view: Any
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View update not supported via datacloud-data SDK")

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View deletion not supported via datacloud-data SDK")

    # ── Relation CRUD (stub — datacloud-data SDK does not yet support) ──────

    def get_relations(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Return empty list — relations not yet available via SDK."""
        return []

    def get_relation_detail(
        self, base_id: str, scene_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Return None — relation details not yet available via SDK."""
        return None

    def create_relation(self, base_id: str, scene_id: str, rel: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation creation not supported via datacloud-data SDK")

    def update_relation(
        self, base_id: str, scene_id: str, rel_code: str, rel: Any
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation update not supported via datacloud-data SDK")

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation deletion not supported via datacloud-data SDK")

    # ── Action CRUD (stub — datacloud-data SDK does not yet support) ────────

    def get_actions(
        self, base_id: str, scene_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Return empty list — actions not yet available via SDK."""
        return []

    def get_action_detail(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Return None — action details not yet available via SDK."""
        return None

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action: Any
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action creation not supported via datacloud-data SDK")

    def update_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action update not supported via datacloud-data SDK")

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action deletion not supported via datacloud-data SDK")

    # ── Datasource CRUD (stub — datacloud-data SDK does not yet support) ────

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Return empty list — datasources not yet available via SDK."""
        return []

    def get_datasource_detail(
        self, base_id: str, scene_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Return None — datasource details not yet available via SDK."""
        return None

    def create_datasource(self, base_id: str, scene_id: str, ds: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError(
            "Datasource creation not supported via datacloud-data SDK"
        )

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError(
            "Datasource deletion not supported via datacloud-data SDK"
        )

    # ── Scene management (stub — datacloud-data SDK does not yet support) ───

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """Return empty list — scene listing not yet available via SDK."""
        return []

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Return empty list — scene query not yet available via SDK."""
        return []

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Return 0 — scene counting not yet available via SDK."""
        return 0

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict[str, Any]:
        """Return empty scene details — not yet available via SDK."""
        return {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": [],
            "version": None,
        }

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Return empty result — ontology-by-scene query not yet available via SDK."""
        return {"data": [], "totalCount": 0}

    # ── StorageBackend ─────────────────────────────────────────────────────

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store result file bytes, returning a unique file_id.

        Args:
            key: Human-readable file key / name.
            data: Raw bytes to persist.
            metadata: Optional metadata dict (stored as a JSON sidecar).

        Returns:
            A UUID-based file_id for retrieval.
        """
        import json as _json  # noqa: PLC0415

        file_id = uuid.uuid4().hex
        store_dir = self._storage_dir()
        store_dir.mkdir(parents=True, exist_ok=True)

        data_path = store_dir / file_id
        data_path.write_bytes(data)

        if metadata:
            meta_path = store_dir / f"{file_id}.meta"
            meta_path.write_text(
                _json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
            )

        logger.info("Stored result file_id=%s key=%s size=%d", file_id, key, len(data))
        return file_id

    def get_result(self, file_id: str) -> bytes:
        """Get result file bytes by ID.

        Args:
            file_id: The file identifier returned by :meth:`store_result`.

        Returns:
            Raw bytes of the stored file.

        Raises:
            FileNotFoundError: If the file_id does not exist.
        """
        data_path = self._storage_dir() / file_id
        if not data_path.exists():
            raise FileNotFoundError(f"Result file not found: {file_id}")
        return data_path.read_bytes()

    def delete_result(self, file_id: str) -> None:
        """Delete a result file by ID.

        Args:
            file_id: The file identifier to delete.
        """
        data_path = self._storage_dir() / file_id
        meta_path = self._storage_dir() / f"{file_id}.meta"
        if data_path.exists():
            data_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        logger.info("Deleted result file_id=%s", file_id)

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List stored result files, optionally filtered by prefix.

        Args:
            prefix: Optional key prefix filter.

        Returns:
            List of StoredFile summaries.
        """
        store_dir = self._storage_dir()
        if not store_dir.exists():
            return []

        files: list[StoredFile] = []
        for entry in sorted(store_dir.iterdir()):
            if entry.is_dir() or entry.suffix == ".meta":
                continue
            fid = entry.name
            if prefix and not fid.startswith(prefix):
                continue
            stat = entry.stat()
            files.append(
                StoredFile(
                    file_id=fid,
                    key=fid,
                    size_bytes=stat.st_size,
                    created_at=str(stat.st_ctime),
                )
            )
        return files

    # ── internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _to_summary(ont_class: object) -> ObjectSummary:
        """Convert an OntologyClass-like object to ObjectSummary.

        References the same attribute names as local_adapter._ontology_class_to_summary.
        """
        object_code: str = getattr(ont_class, "object_code", "")
        object_name: str = getattr(ont_class, "object_name", "")
        description: str = getattr(ont_class, "description", "")
        source_type: str = getattr(ont_class, "source_type", "")
        field_count: int = len(getattr(ont_class, "fields", []))
        action_count: int = len(getattr(ont_class, "actions", []))
        return ObjectSummary(
            object_code=object_code,
            object_name=object_name,
            description=description,
            object_source=source_type,
            field_count=field_count,
            action_count=action_count,
        )

    @staticmethod
    def _storage_dir() -> Path:
        """Resolve storage directory from env or default."""
        env_dir = os.getenv(_STORAGE_DIR_ENV)
        if env_dir:
            return Path(env_dir)
        return Path(_DEFAULT_STORAGE_DIR)
