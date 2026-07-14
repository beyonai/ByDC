"""OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.adapters.data_adapter._base import (
    DataCloudDataBackendBase,
    _normalize_entity,
    _normalize_object_codes,
    _DEFAULT_DYNAMIC_DATASOURCE_ALIAS,
)
from datacloud_platform.models import ObjectSummary, ParsedOwlContent
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)


def _ensure_default_datasource(loader: Any, objects: list[dict[str, Any]]) -> None:
    """Register a default SQLite datasource if DYNAMIC_TABLE objects exist but
    no datasource configs have been loaded.

    The DynamicTableExecutor requires a named datasource registered in
    DataSourceManager.  Without an OWL file, API-created bases have no
    datasource configs — this provides a fallback SQLite connector pointing
    at the same ``personal_object.db`` used by ``create_table``.
    """
    existing = getattr(loader._config, "datasource_configs", {}) or {}
    # Always register/overwrite: _extract_datasource_configs_from_objects may
    # have created a config for this alias without jdbc_url (from source_config),
    # and the SQLiteConnector requires a valid jdbc_url.

    # Resolve the SQLite path.  create_table uses FILE_STORAGE_MINIO_MOUNT_PATH
    # to locate personal_object.db; we need the same path for consistency.
    mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
    if not mount:
        logger.warning(
            "FILE_STORAGE_MINIO_MOUNT_PATH not set — cannot register default SQLite datasource"
        )
        return
    db_path = os.path.join(mount, "byclaw-datacloud", "personal_object.db")

    # Match the format expected by DataSourceManager._dict_to_config / SQLiteConnector
    from datacloud_data_sdk.sql_executor.config_loader import (  # noqa: PLC0415
        _dict_to_config,
    )

    # Ensure the parent directory exists (create_table does this too, but
    # load_ontology may run before any table is created).
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    existing[_DEFAULT_DYNAMIC_DATASOURCE_ALIAS] = _dict_to_config(
        _DEFAULT_DYNAMIC_DATASOURCE_ALIAS,
        {
            "db_type": "SQLITE",
            "jdbc_url": f"jdbc:sqlite:{db_path}",
            "ds_name": "Dynamic Table Default",
        },
    )
    loader._config.datasource_configs = existing


class OntologyBackendMixin(DataCloudDataBackendBase):
    """OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

    # ── OntologyBackend ────────────────────────────────────────────────────

    def parse_owl(self, directory: Path) -> ParsedOwlContent:
        """Parse OWL directory via OwlParser, return typed ParsedOwlContent.

        Args:
            directory: Path to the OWL resource directory.

        Returns:
            ParsedOwlContent with objects, views, relations, actions, dbsources.
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser  # noqa: PLC0415

        raw: dict[str, Any] = OwlParser().parse_resource_directory(directory)
        objects = list(raw.get("objects", []))
        views = list(raw.get("views", []))
        relations = list(raw.get("relations", []))

        # Extract actions from embedded object.actions, adding belongObjectCode
        actions: list[dict[str, Any]] = []
        for obj in objects:
            obj_code = obj.get("object_code", "")
            for act in obj.get("actions", []):
                if isinstance(act, dict):
                    act = dict(act)
                    act.setdefault("belongObjectCode", obj_code)
                    actions.append(act)

        # Extract dbsources from datasource_configs dict
        dbsources: list[dict[str, Any]] = []
        raw_ds: dict[str, dict[str, Any]] = raw.get("datasource_configs", {}) or {}
        for alias, cfg in raw_ds.items():
            dbsources.append(dict(cfg, alias=alias))

        return ParsedOwlContent(
            objects=objects,
            views=views,
            relations=relations,
            actions=actions,
            dbsources=dbsources,
        )

    def batch_import_ontology(
        self,
        base_path: Path,
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        dbsources: list[dict[str, Any]],
        *,
        base_id: str = "",
    ) -> dict[str, int]:
        """Batch import ontology content — writes registry + shard files + rebuilds indexes.

        Args:
            base_path: Root directory for the ontology base.
            objects: List of object dicts to persist.
            views: List of view dicts to persist.
            relations: List of relation dicts to persist.
            actions: List of action dicts to persist.
            dbsources: List of datasource dicts to persist.

        Returns:
            Counts dict keyed by entity type.
        """
        entity_store = self._entity_store.sub_store(base_id or base_path.name)

        counts: dict[str, int] = {
            "objects": 0,
            "views": 0,
            "relations": 0,
            "actions": 0,
            "dbsources": 0,
        }

        # Batch-write entities via save_batch (EntityStore handles index + version)
        entity_store.save_batch(
            "objects",
            [(o.get("object_code", ""), o) for o in objects if o.get("object_code")],
        )
        counts["objects"] = sum(1 for o in objects if o.get("object_code"))
        entity_store.save_batch(
            "views",
            [
                (v.get("view_code") or v.get("viewCode") or v.get("view_id", ""), v)
                for v in views
                if v.get("view_code") or v.get("viewCode") or v.get("view_id", "")
            ],
        )
        counts["views"] = sum(
            1
            for v in views
            if v.get("view_code") or v.get("viewCode") or v.get("view_id", "")
        )
        entity_store.save_batch(
            "relations",
            [
                (r.get("relation_code") or r.get("relationCode", ""), r)
                for r in relations
                if r.get("relation_code") or r.get("relationCode", "")
            ],
        )
        counts["relations"] = sum(
            1 for r in relations if r.get("relation_code") or r.get("relationCode", "")
        )
        entity_store.save_batch(
            "actions",
            [
                (a.get("action_code") or a.get("actionCode", ""), a)
                for a in actions
                if a.get("action_code") or a.get("actionCode", "")
            ],
        )
        counts["actions"] = sum(
            1 for a in actions if a.get("action_code") or a.get("actionCode", "")
        )
        entity_store.save_batch(
            "datasources",
            [
                (d.get("db_id") or d.get("dbId", ""), d)
                for d in dbsources
                if d.get("db_id") or d.get("dbId", "")
            ],
        )
        counts["dbsources"] = sum(
            1 for d in dbsources if d.get("db_id") or d.get("dbId", "")
        )

        # Batch sync terms to knowledge DB (single writer, no per-term backfill)
        t_sync = time.monotonic()
        self._batch_sync_entity_terms(objects, views, relations, actions)
        logger.warning(
            "_batch_sync_entity_terms done in %.1fs", time.monotonic() - t_sync
        )

        logger.info(
            "batch_import_ontology: %s objects=%d views=%d relations=%d actions=%d dbsources=%d",
            base_path,
            counts["objects"],
            counts["views"],
            counts["relations"],
            counts["actions"],
            counts["dbsources"],
        )
        return counts

    def load_ontology(self, base_path: Path, *, base_id: str = "") -> OntologyQueryable:
        """Load ontology from EntityStore into a queryable runtime object.

        Reads all entity types from the store and assembles an OntologyLoader.
        Falls back to OWL parsing when the store has no data for this base.

        Args:
            base_path: Path to the OWL resource directory root
                       (used for OWL fallback).
            base_id: Explicit base namespace key.  When empty, falls back to
                     ``base_path.name`` (backward-compatible with JSON store).

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        base_id = base_id or base_path.name
        store = self._entity_store.sub_store(base_id)

        # Build registry-like content from store (single query per entity type)
        t0 = time.monotonic()
        all_objects = store.list_all("objects")
        all_views = store.list_all("views")
        all_relations = store.list_all("relations")
        all_actions = store.list_all("actions")
        all_dbsources = store.list_all("datasources")
        logger.warning(
            "loaded entities: objects=%d views=%d relations=%d actions=%d dbsources=%d in %.1fs",
            len(all_objects),
            len(all_views),
            len(all_relations),
            len(all_actions),
            len(all_dbsources),
            time.monotonic() - t0,
        )

        if any([all_objects, all_views, all_relations, all_actions, all_dbsources]):
            # Normalize legacy camelCase keys to snake_case for all entity types.
            # Filtered lists contain no None at runtime (see [a for a in ... if a] above),
            # but mypy cannot narrow through list comprehension reassignment.
            _obj_map = {"objectCode": "object_code"}
            _view_map = {"viewCode": "view_code", "viewId": "view_code"}
            _rel_map = {"relationCode": "relation_code"}
            _act_map = {"actionCode": "action_code"}
            self._normalize_entity_keys(all_objects, _obj_map)
            self._normalize_entity_keys(all_views, _view_map)
            self._normalize_entity_keys(all_relations, _rel_map)
            self._normalize_entity_keys(all_actions, _act_map)

            # OntologyLoader uses view["view_id"] as the dict key (line 365/434),
            # but normalization only sets view_code.  Mirror view_code → view_id
            # so loader._views keys match get_view_detail() lookups.
            for v in all_views:
                if "view_id" not in v:
                    v["view_id"] = v.get("view_code", "")

            # Patch DYNAMIC_TABLE objects missing datasource_alias so the executor
            # can find a connector.  Objects created via API (no OWL) don't have
            # one set, and the default datasource is registered below.
            for o in all_objects:
                st = (o.get("source_type") or o.get("objectSource") or "").upper()
                if st == "DYNAMIC_TABLE" and not o.get("datasource_alias"):
                    o["datasource_alias"] = _DEFAULT_DYNAMIC_DATASOURCE_ALIAS
                    o.setdefault("table_name", o.get("object_code", ""))

            loader = OntologyLoader()
            loader.load_from_content(
                {
                    "objects": all_objects,
                    "views": all_views,
                    "relations": all_relations,
                    "actions": all_actions,
                    "dbsources": all_dbsources,
                }
            )
            # Register the default SQLite datasource so DynamicTableExecutor can
            # connect.  Must happen after load_from_content so the loader's config
            # is initialised.
            _ensure_default_datasource(loader, all_objects)
            return loader  # type: ignore[return-value]

        # Fallback: OWL directory exists but store is empty
        if base_path.exists():
            logger.warning(
                "Store empty for base_id=%s, falling back to parse_owl + batch_import_ontology",
                base_id,
            )
            t1 = time.monotonic()
            parsed = self.parse_owl(base_path)
            logger.warning(
                "parse_owl done in %.1fs, objects=%d views=%d relations=%d actions=%d dbsources=%d",
                time.monotonic() - t1,
                len(parsed.objects),
                len(parsed.views),
                len(parsed.relations),
                len(parsed.actions),
                len(parsed.dbsources),
            )
            t2 = time.monotonic()
            self.batch_import_ontology(
                base_path,
                parsed.objects,
                parsed.views,
                parsed.relations,
                parsed.actions,
                parsed.dbsources,
                base_id=base_id,
            )
            logger.warning("batch_import_ontology done in %.1fs", time.monotonic() - t2)
            return self.load_ontology(
                base_path, base_id=base_id
            )  # recurse → store now has data

        # No OWL directory, return empty loader
        return OntologyLoader()  # type: ignore[return-value]

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
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ObjectSummary], int]:
        """Get paginated object summaries under a base with optional filtering.

        Args:
            base_id: Base / project identifier.
            owner_type: Filter by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on name/code/description.
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            Tuple of (paginated ObjectSummary list, total matching count).
        """
        store = self._entity_store.sub_store(base_id)
        # Use list_all for accurate filtering (search only matches name/index keys)
        all_items = store.list_all("objects")
        summaries: list[ObjectSummary] = []
        for raw in all_items:
            summary = self._raw_to_summary(raw)
            if owner_type and summary.owner_type != owner_type:
                continue
            if owner_type == "personal" and user_code:
                if summary.user_code != user_code:
                    continue
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in summary.object_name.lower()
                    and kw not in summary.object_code.lower()
                    and kw not in summary.description.lower()
                ):
                    continue
            summaries.append(summary)
        total = len(summaries)
        offset = (page - 1) * page_size
        return summaries[offset : offset + page_size], total

    def get_object_detail(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get full object detail with properties and actions from the entity store.

        Args:
            object_code: The object code to look up.
            base_id: Base / project identifier.

        Returns:
            Full ObjectType dict (alias-mapped) if found, otherwise None.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("objects", object_code)
        if raw is None:
            return None
        return self.get_object_detail_from_raw(raw, object_code)

    def get_object_detail_from_raw(
        self, raw: dict[str, Any], object_code: str
    ) -> dict[str, Any] | None:
        """Get full object detail from a single raw entity dict — no full ontology load.

        Uses OntologyLoader to parse just this one object, then extracts the
        resulting OntologyClass.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        # Normalize legacy camelCase data (model_dump by_alias) and OWL data
        # into the canonical snake_case format that OntologyLoader expects.
        normalized = _normalize_entity("object", raw)
        loader = OntologyLoader()
        loader.load_from_content({"objects": [normalized]})
        cls = loader._classes.get(object_code)
        if cls is None:
            return None
        # Inject owner_type/user_code from raw dict top-level keys:
        # create_object stores them at the root, not in ext_property, and
        # OntologyLoader does not pass them to OntologyClass.
        ext: dict[str, Any] = cls.ext_property
        for key in ("owner_type", "ownerType"):
            if key in raw and "owner_type" not in ext:
                ext["owner_type"] = raw[key]
        for key in ("user_code", "userCode"):
            if key in raw and "user_code" not in ext:
                ext["user_code"] = raw[key]
        return self._build_object_detail(cls)

    @staticmethod
    def _build_object_detail(cls: Any) -> dict[str, Any]:
        """Build ObjectType dict from a parsed OntologyClass."""
        ext: dict[str, Any] = getattr(cls, "ext_property", {}) or {}
        obj = ObjectType(
            objectCode=cls.object_code,
            objectName=cls.object_name,
            objectDesc=getattr(cls, "description", None),
            objectSource=getattr(cls, "source_type", None),
            conceptType=getattr(cls, "concept_type", None),
            ownerType=(
                ext.get("owner_type")
                or getattr(cls, "owner_type", None)
                or "enterprise"
            ),
            userCode=(ext.get("user_code") or getattr(cls, "user_code", None)),
            baseId="",
            ext_property=ext,
            properties=[
                Property(
                    propertyName=f.field_name,
                    propertyCode=f.field_code,
                    propertyDesc=getattr(f, "description", None) or None,
                    dataType=f.field_type,
                    dataFormat=getattr(f, "data_format", None),
                    isRequired=1 if getattr(f, "required", False) else 0,
                    businessKey=1 if f.is_primary_key else 0,
                    sourceColumn=getattr(f, "source_column", None),
                    dbId=getattr(cls, "datasource_alias", None),
                )
                for f in cls.fields
            ],
            actions=[
                Action(
                    actionCode=a.action_code,
                    actionName=a.action_name,
                    actionType=a.action_type,
                    belongObjectCode=a.belong_class,
                    actionDesc=getattr(a, "description", None),
                    requestUrl=getattr(a, "request_url", None),
                    requestMethod=getattr(a, "request_method", None),
                    params=[
                        ActionParam(
                            paramCode=p.param_code,
                            paramName=p.param_name,
                            paramType=getattr(p, "param_type", None),
                            isRequired=1 if p.required else 0,
                            direction=getattr(p, "direction", None),
                            mappingPath=getattr(p, "mapping_path", None),
                        )
                        for p in getattr(a, "params", [])
                    ],
                )
                for a in getattr(cls, "actions", [])
            ],
        )
        return obj.model_dump(by_alias=True)

    @staticmethod
    def _raw_to_summary(raw: dict[str, Any]) -> ObjectSummary:
        """Convert a raw object dict from the store to ObjectSummary."""
        ext = raw.get("ext_property", {}) or {}
        owner: str = (
            ext.get("owner_type")
            or raw.get("owner_type")
            or raw.get("ownerType", "enterprise")
        ) or "enterprise"
        user: str | None = (
            ext.get("user_code") or raw.get("user_code") or raw.get("userCode")
        )
        return ObjectSummary(
            object_code=raw.get("object_code", raw.get("objectCode", "")),
            object_name=raw.get("object_name", raw.get("objectName", "")),
            description=raw.get("description", raw.get("objectDesc", "")) or "",
            object_source=raw.get("source_type", raw.get("sourceType", "")) or "",
            field_count=len(raw.get("fields", [])),
            action_count=len(raw.get("actions", [])),
            owner_type=owner,
            user_code=user,
        )

    # ── Object CRUD (stub — datacloud-data SDK does not yet support) ────────

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Persist a new ontology object via EntityStore.

        Args:
            base_id: Base / project identifier.
            obj: ObjectType dict or pydantic model.

        Returns:
            The saved object dict.

        Raises:
            ValueError: If object_code is missing or empty.
        """
        entity_store = self._entity_store.sub_store(base_id)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        code: str = obj_dict.get("object_code") or obj_dict.get("objectCode", "")
        if not code:
            raise ValueError("object_code is required for object creation")
        # Normalize owner_type/user_code
        _owner_type: str = obj_dict.get("ownerType") or obj_dict.get(
            "owner_type", "enterprise"
        )
        _user_code: str | None = obj_dict.get("userCode") or obj_dict.get("user_code")
        obj_dict["ownerType"] = _owner_type
        obj_dict["owner_type"] = _owner_type
        if _user_code:
            obj_dict["userCode"] = _user_code
            obj_dict["user_code"] = _user_code
        # Canonicalize before save — ensures fields/properties, camelCase/snake_case
        # are consistent regardless of whether obj came from API or OWL.
        obj_dict = _normalize_entity("object", obj_dict, for_storage=True)
        entity_store.save("objects", code, obj_dict)
        logger.info("Created object: base_id=%s object_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="object",
            entity_code=code,
            entity_name=obj_dict.get("objectName") or obj_dict.get("object_name", code),
            entity_desc=obj_dict.get("objectDesc") or obj_dict.get("description", ""),
            fields=obj_dict.get("fields", []),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_create",
            "OBJECT",
            resource_code=code,
            resource_name=obj_dict.get("objectName")
            or obj_dict.get("object_name", code),
            resource_desc=(
                obj_dict.get("objectDesc")
                or obj_dict.get("object_desc", "")
                or obj_dict.get("description", "")
            ),
            base_code=base_id,
            owner_type=obj_dict.get("ownerType")
            or obj_dict.get("owner_type", "enterprise"),
        )
        return obj_dict

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update an existing ontology object.

        Args:
            base_id: Base / project identifier.
            object_code: Target object code.
            obj: Updated ObjectType dict or pydantic model.

        Returns:
            The updated object dict.
        """
        entity_store = self._entity_store.sub_store(base_id)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        # Normalize owner_type/user_code
        _owner_type: str = obj_dict.get("ownerType") or obj_dict.get(
            "owner_type", "enterprise"
        )
        _user_code: str | None = obj_dict.get("userCode") or obj_dict.get("user_code")
        obj_dict["ownerType"] = _owner_type
        obj_dict["owner_type"] = _owner_type
        if _user_code:
            obj_dict["userCode"] = _user_code
            obj_dict["user_code"] = _user_code
        obj_dict = _normalize_entity("object", obj_dict, for_storage=True)
        entity_store.save("objects", object_code, obj_dict)
        logger.info("Updated object: base_id=%s object_code=%s", base_id, object_code)
        # Re-sync terms: delete old → write new (build_terms is upsert-safe)
        self._remove_entity_terms(entity_type="object", entity_code=object_code)
        self._sync_entity_terms(
            entity_type="object",
            entity_code=object_code,
            entity_name=obj_dict.get("objectName")
            or obj_dict.get("object_name", object_code),
            entity_desc=obj_dict.get("objectDesc") or obj_dict.get("description", ""),
            fields=obj_dict.get("fields", []),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_update",
            "OBJECT",
            resource_code=object_code,
            resource_name=obj_dict.get("objectName")
            or obj_dict.get("object_name", object_code),
            resource_desc=obj_dict.get("objectDesc") or obj_dict.get("object_desc", ""),
            base_code=base_id,
            owner_type=obj_dict.get("ownerType")
            or obj_dict.get("owner_type", "enterprise"),
        )
        return obj_dict

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Delete an ontology object.

        Args:
            base_id: Base / project identifier.
            object_code: Target object code.
        """
        entity_store = self._entity_store.sub_store(base_id)
        entity_store.delete("objects", object_code)
        logger.info("Deleted object: base_id=%s object_code=%s", base_id, object_code)
        self._remove_entity_terms(entity_type="object", entity_code=object_code)
        self._invoke_sync_hook(
            "on_delete",
            "OBJECT",
            resource_code=object_code,
            base_code=base_id,
        )

    # ── View CRUD ──────────────────────────────────────────────────────────

    def _raw_to_view_dict(
        self,
        raw: dict[str, Any],
        view_code: str = "",
    ) -> dict[str, Any]:
        """Convert a raw view dict from the store to a View model dict."""
        vc = (
            view_code
            or raw.get("view_code")
            or raw.get("viewCode")
            or raw.get("view_id", "")
        )
        ext = raw.get("ext_property", {}) or {}
        v_owner: str = (
            ext.get("owner_type")
            or raw.get("owner_type")
            or raw.get("ownerType", "enterprise")
        ) or "enterprise"
        v_user: str | None = (
            ext.get("user_code") or raw.get("user_code") or raw.get("userCode")
        )
        normalized_codes = _normalize_object_codes(raw.get("objects", []))
        view = View(
            viewCode=raw.get("view_id", vc),
            viewName=raw.get("view_name", "") or "",
            description=raw.get("description"),
            objectCodes=normalized_codes,
            ownerType=v_owner,
            userCode=v_user,
            properties=[
                ViewProperty(
                    propertyName=m.get("property_name", ""),
                    propertyCode=m.get("property_code", ""),
                    sourceObject=m.get("source_object_code", ""),
                    sourceObjectProperty=m.get("source_object_column_code", ""),
                )
                for m in raw.get("mappings", [])
            ],
        )
        return view.model_dump(by_alias=True)

    def get_views(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated views under a base with optional filtering.

        Args:
            base_id: Base / project identifier.
            owner_type: Filter by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on view_name/view_code/description.
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            Tuple of (paginated View dict list, total count).
        """
        store = self._entity_store.sub_store(base_id)
        all_items = store.list_all("views")
        result: list[dict[str, Any]] = []
        for raw in all_items:
            view_dict = self._raw_to_view_dict(raw)
            v_owner: str = view_dict.get("ownerType", "enterprise")
            if owner_type and v_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                v_user: str | None = view_dict.get("userCode")
                if v_user != user_code:
                    continue
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in (view_dict.get("viewName", "") or "").lower()
                    and kw not in (view_dict.get("viewCode", "") or "").lower()
                    and kw not in (view_dict.get("description", "") or "").lower()
                ):
                    continue
            result.append(view_dict)
        total = len(result)
        offset = (page - 1) * page_size
        return result[offset : offset + page_size], total

    def get_view_detail(
        self, view_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single view detail by code from the entity store.

        Args:
            view_code: View identifier to look up.
            base_id: Base / project identifier.

        Returns:
            View dict if found, otherwise None.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("views", view_code)
        if raw is None:
            return None
        return self._raw_to_view_dict(raw, view_code)

    def get_objects_by_view(
        self,
        view_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get object summaries referenced by a view — from entity store.

        Args:
            view_code: View code to look up.
            base_id: Base / project identifier.
            owner_type: Filter objects by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on object_name/object_code/description.

        Returns:
            List of object dicts with objectCode/objectName/objectDesc/ownerType/userCode.
        """
        store = self._entity_store.sub_store(base_id)
        view_raw = store.get("views", view_code)
        if view_raw is None:
            return []

        normalized_codes = _normalize_object_codes(view_raw.get("objects", []))
        result: list[dict[str, Any]] = []
        for code in normalized_codes:
            raw = store.get("objects", code)
            if raw is None:
                continue
            summary = self._raw_to_summary(raw)
            if owner_type and summary.owner_type != owner_type:
                continue
            if owner_type == "personal" and user_code:
                if summary.user_code != user_code:
                    continue
            obj_dict: dict[str, Any] = {
                "objectCode": summary.object_code,
                "objectName": summary.object_name,
                "objectDesc": summary.description,
                "ownerType": summary.owner_type,
                "userCode": summary.user_code,
            }
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in summary.object_name.lower()
                    and kw not in summary.object_code.lower()
                    and kw not in summary.description.lower()
                ):
                    continue
            result.append(obj_dict)
        return result

    def create_view(self, base_id: str, view: Any) -> Any:
        """Persist a new view via EntityStore.

        Args:
            base_id: Base / project identifier.
            view: View dict or pydantic model.

        Returns:
            The saved view dict.

        Raises:
            ValueError: If view_code is missing or empty.
        """
        entity_store = self._entity_store.sub_store(base_id)
        view_dict: dict[str, Any] = (
            view if isinstance(view, dict) else view.model_dump(by_alias=True)
        )
        code: str = (
            view_dict.get("view_code")
            or view_dict.get("viewCode")
            or view_dict.get("view_id", "")
        )
        if not code:
            raise ValueError("view_code is required for view creation")
        view_dict = _normalize_entity("view", view_dict, for_storage=True)
        entity_store.save("views", code, view_dict)
        logger.info("Created view: base_id=%s view_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=code,
            entity_name=view_dict.get("viewName") or view_dict.get("view_name", code),
            entity_desc=view_dict.get("description", ""),
            fields=view_dict.get("mappings", []),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_create",
            "VIEW",
            resource_code=code,
            resource_name=view_dict.get("viewName") or view_dict.get("view_name", code),
            resource_desc=view_dict.get("description", ""),
            base_code=base_id,
            owner_type=view_dict.get("ownerType")
            or view_dict.get("owner_type", "enterprise"),
        )
        return view_dict

    def update_view(self, base_id: str, view_code: str, view: Any) -> Any:
        """Update an existing view.

        Args:
            base_id: Base / project identifier.
            view_code: Target view code.
            view: Updated View dict or pydantic model.

        Returns:
            The updated view dict.
        """
        entity_store = self._entity_store.sub_store(base_id)
        view_dict: dict[str, Any] = (
            view if isinstance(view, dict) else view.model_dump(by_alias=True)
        )
        view_dict = _normalize_entity("view", view_dict, for_storage=True)
        entity_store.save("views", view_code, view_dict)
        logger.info("Updated view: base_id=%s view_code=%s", base_id, view_code)
        self._remove_entity_terms(entity_type="view", entity_code=view_code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=view_code,
            entity_name=view_dict.get("viewName")
            or view_dict.get("view_name", view_code),
            entity_desc=view_dict.get("description", ""),
            fields=view_dict.get("mappings", []),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_update",
            "VIEW",
            resource_code=view_code,
            resource_name=view_dict.get("viewName")
            or view_dict.get("view_name", view_code),
            resource_desc=view_dict.get("description", ""),
            base_code=base_id,
            owner_type=view_dict.get("ownerType")
            or view_dict.get("owner_type", "enterprise"),
        )
        return view_dict

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Delete a view.

        Args:
            base_id: Base / project identifier.
            view_code: Target view code.
        """
        entity_store = self._entity_store.sub_store(base_id)
        entity_store.delete("views", view_code)
        logger.info("Deleted view: base_id=%s view_code=%s", base_id, view_code)
        self._remove_entity_terms(entity_type="view", entity_code=view_code)
        self._invoke_sync_hook(
            "on_delete",
            "VIEW",
            resource_code=view_code,
            base_code=base_id,
        )

    # ── Relation CRUD ───────────────────────────────────────────────

    def _raw_to_relation_dict(
        self,
        raw: dict[str, Any],
        store: Any,
    ) -> dict[str, Any]:
        """Convert a raw relation dict to a Relation model dict, resolving object names."""
        src = raw.get("source_class", "")
        tgt = raw.get("target_class", "")
        # Resolve names from object store
        src_name = ""
        tgt_name = ""
        src_obj = store.get("objects", src)
        if src_obj:
            src_name = src_obj.get("object_name", src_obj.get("objectName", "")) or ""
        tgt_obj = store.get("objects", tgt)
        if tgt_obj:
            tgt_name = tgt_obj.get("object_name", tgt_obj.get("objectName", "")) or ""

        rel = Relation(
            relationCode=raw.get("relation_code", raw.get("relationCode", "")),
            relationName=raw.get("relation_name") or raw.get("relationName"),
            sourceObjectCode=src,
            targetObjectCode=tgt,
            relationCardinality=raw.get("relation_type")
            or raw.get("relationCardinality"),
            sourceObjectName=src_name,
            targetObjectName=tgt_name,
            relationDesc=raw.get("relation_desc")
            or raw.get("description")
            or raw.get("relationDesc"),
            relationSceneType=raw.get("relation_scene_type")
            or raw.get("relationSceneType"),
            ownerType=str(raw.get("owner_type", raw.get("ownerType", "enterprise"))),
            userCode=raw.get("user_code") or raw.get("userCode"),
        )
        return rel.model_dump(by_alias=True)

    def get_relations(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated relations under a base with optional filtering.

        Args:
            base_id: Base / project identifier.
            owner_type: Filter by owner_type.
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on relation_name/code/description.
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            Tuple of (paginated Relation dict list, total count).
        """
        store = self._entity_store.sub_store(base_id)
        all_items = store.list_all("relations")
        result: list[dict[str, Any]] = []
        for raw in all_items:
            rel_dict = self._raw_to_relation_dict(raw, store)
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in (rel_dict.get("relationName", "") or "").lower()
                    and kw not in (rel_dict.get("relationCode", "") or "").lower()
                    and kw not in (rel_dict.get("relationDesc", "") or "").lower()
                ):
                    continue
            if owner_type and rel_dict.get("ownerType", "enterprise") != owner_type:
                continue
            if owner_type == "personal" and user_code:
                if rel_dict.get("userCode") != user_code:
                    continue
            result.append(rel_dict)
        total = len(result)
        offset = (page - 1) * page_size
        return result[offset : offset + page_size], total

    def get_relation_detail(
        self, rel_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the entity store.

        Args:
            rel_code: Relation code to look up.
            base_id: Base / project identifier.

        Returns:
            Relation dict if found, otherwise None.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("relations", rel_code)
        if raw is None:
            return None
        return self._raw_to_relation_dict(raw, store)

    def get_relations_by_object(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relation details involving *object_code* (source or target).

        Args:
            object_code: Object to find relations for (bidirectional).
            base_id: Base / project identifier.
            owner_type: Filter relations by owner_type.
            user_code: Filter by user_code when owner_type is personal.

        Returns:
            List of relation dicts (full detail, alias-mapped).
        """
        store = self._entity_store.sub_store(base_id)
        all_items = store.list_all("relations")
        result: list[dict[str, Any]] = []
        for raw in all_items:
            rel_dict = self._raw_to_relation_dict(raw, store)
            src: str = rel_dict.get("sourceObjectCode", "")
            tgt: str = rel_dict.get("targetObjectCode", "")
            if src != object_code and tgt != object_code:
                continue
            rel_owner: str = rel_dict.get("ownerType", "enterprise")
            if owner_type and rel_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                rel_user: str | None = rel_dict.get("userCode")
                if rel_user != user_code:
                    continue
            result.append(rel_dict)
        return result

    def create_relation(self, base_id: str, rel: Any) -> Any:
        """Persist a new relation via EntityStore.

        Args:
            base_id: Base / project identifier.
            rel: Relation dict or pydantic model.

        Returns:
            The saved relation dict.

        Raises:
            ValueError: If relation_code is missing or empty.
        """
        entity_store = self._entity_store.sub_store(base_id)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        code: str = rel_dict.get("relation_code") or rel_dict.get("relationCode", "")
        if not code:
            raise ValueError("relation_code is required for relation creation")
        rel_dict = _normalize_entity("relation", rel_dict, for_storage=True)
        entity_store.save("relations", code, rel_dict)
        logger.info("Created relation: base_id=%s relation_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="relation",
            entity_code=code,
            entity_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", code),
            entity_desc=rel_dict.get("relationDesc") or rel_dict.get("description", ""),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_create",
            "RELATION",
            resource_code=code,
            resource_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", code),
            resource_desc=rel_dict.get("relationDesc")
            or rel_dict.get("relation_desc", ""),
            base_code=base_id,
        )
        return rel_dict

    def update_relation(self, base_id: str, rel_code: str, rel: Any) -> Any:
        """Update an existing relation.

        Args:
            base_id: Base / project identifier.
            rel_code: Target relation code.
            rel: Updated Relation dict or pydantic model.

        Returns:
            The updated relation dict.
        """
        entity_store = self._entity_store.sub_store(base_id)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        rel_dict = _normalize_entity("relation", rel_dict, for_storage=True)
        entity_store.save("relations", rel_code, rel_dict)
        logger.info("Updated relation: base_id=%s rel_code=%s", base_id, rel_code)
        self._remove_entity_terms(entity_type="relation", entity_code=rel_code)
        self._sync_entity_terms(
            entity_type="relation",
            entity_code=rel_code,
            entity_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", rel_code),
            entity_desc=rel_dict.get("relationDesc") or rel_dict.get("description", ""),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_update",
            "RELATION",
            resource_code=rel_code,
            resource_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", rel_code),
            resource_desc=rel_dict.get("relationDesc")
            or rel_dict.get("relation_desc", ""),
            base_code=base_id,
        )
        return rel_dict

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Delete a relation.

        Args:
            base_id: Base / project identifier.
            rel_code: Target relation code.
        """
        entity_store = self._entity_store.sub_store(base_id)
        entity_store.delete("relations", rel_code)
        logger.info("Deleted relation: base_id=%s rel_code=%s", base_id, rel_code)
        self._remove_entity_terms(entity_type="relation", entity_code=rel_code)
        self._invoke_sync_hook(
            "on_delete",
            "RELATION",
            resource_code=rel_code,
            base_code=base_id,
        )

    # ── Action CRUD ─────────────────────────────────────────────────

    def _raw_actions_to_dicts(self, raw_obj: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert a raw object dict's actions list to Action model dicts."""
        actions_raw: list[dict[str, Any]] = raw_obj.get("actions", [])
        result: list[dict[str, Any]] = []
        for a in actions_raw:
            ext = a.get("ext_property", {}) or {}
            act = Action(
                actionCode=a.get("action_code", a.get("actionCode", "")),
                actionName=a.get("action_name", a.get("actionName", "")),
                actionType=a.get("action_type", a.get("actionType", "")),
                belongObjectCode=a.get(
                    "belongObjectCode",
                    a.get("belong_object_code", raw_obj.get("object_code", "")),
                ),
                actionDesc=a.get("description") or a.get("actionDesc"),
                requestUrl=a.get("request_url") or a.get("requestUrl"),
                requestMethod=a.get("request_method") or a.get("requestMethod"),
                ownerType=ext.get("owner_type")
                or a.get("owner_type")
                or a.get("ownerType", "enterprise"),
                userCode=ext.get("user_code")
                or a.get("user_code")
                or a.get("userCode"),
                params=[
                    ActionParam(
                        paramCode=p.get("param_code", p.get("paramCode", "")),
                        paramName=p.get("param_name", p.get("paramName", "")),
                        paramType=p.get("param_type") or p.get("paramType"),
                        isRequired=1 if p.get("required", False) else 0,
                        direction=p.get("direction"),
                        mappingPath=p.get("mapping_path") or p.get("mappingPath"),
                    )
                    for p in a.get("params", [])
                ],
            )
            result.append(act.model_dump(by_alias=True))
        return result

    def get_actions(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for an object from the entity store with optional filtering.

        Args:
            object_code: Target object code.
            base_id: Base / project identifier.
            owner_type: Filter by owner_type.
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on action_name/code/description.

        Returns:
            List of Action dicts (by_alias=True).
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("objects", object_code)
        if raw is None:
            return []
        result = self._raw_actions_to_dicts(raw)
        # Filter by owner_type/user_code
        if owner_type:
            result = [
                a for a in result if a.get("ownerType", "enterprise") == owner_type
            ]
        if owner_type == "personal" and user_code:
            result = [a for a in result if a.get("userCode") == user_code]
        if keyword:
            kw = keyword.strip().lower()
            result = [
                a
                for a in result
                if kw in (a.get("actionName", "") or "").lower()
                or kw in (a.get("actionCode", "") or "").lower()
                or kw in (a.get("actionDesc", "") or "").lower()
            ]
        return result

    def get_action_detail(
        self,
        object_code: str,
        action_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Get single action detail by code from the entity store.

        Args:
            object_code: Parent object code.
            action_code: Action code to look up.
            base_id: Base / project identifier.

        Returns:
            Action dict if found, otherwise None.
        """
        for a in self.get_actions(object_code, base_id=base_id):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(self, base_id: str, object_code: str, action: Any) -> Any:
        """Persist a new action under an object via EntityStore.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action: Action dict or pydantic model.

        Returns:
            The saved action dict.

        Raises:
            ValueError: If action_code is missing or empty.
        """
        entity_store = self._entity_store.sub_store(base_id)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        code: str = action_dict.get("action_code") or action_dict.get("actionCode", "")
        if not code:
            raise ValueError("action_code is required for action creation")
        # Ensure parent object_code is recorded
        action_dict["belongObjectCode"] = object_code
        action_dict = _normalize_entity("action", action_dict, for_storage=True)
        entity_store.save("actions", code, action_dict)
        logger.info(
            "Created action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            code,
        )
        self._sync_entity_terms(
            entity_type="ontology_action",
            entity_code=code,
            entity_name=action_dict.get("actionName")
            or action_dict.get("action_name", code),
            entity_desc=action_dict.get("actionDesc")
            or action_dict.get("description", ""),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_create",
            "ACTION",
            resource_code=code,
            resource_name=action_dict.get("actionName")
            or action_dict.get("action_name", code),
            resource_desc=action_dict.get("actionDesc")
            or action_dict.get("action_desc", ""),
            base_code=base_id,
        )
        return action_dict

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Update an existing action.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action_code: Target action code.
            action: Updated Action dict or pydantic model.

        Returns:
            The updated action dict.
        """
        entity_store = self._entity_store.sub_store(base_id)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        action_dict["belongObjectCode"] = object_code
        action_dict = _normalize_entity("action", action_dict, for_storage=True)
        entity_store.save("actions", action_code, action_dict)
        logger.info(
            "Updated action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
        )
        self._remove_entity_terms(
            entity_type="ontology_action", entity_code=action_code
        )
        self._sync_entity_terms(
            entity_type="ontology_action",
            entity_code=action_code,
            entity_name=action_dict.get("actionName")
            or action_dict.get("action_name", action_code),
            entity_desc=action_dict.get("actionDesc")
            or action_dict.get("description", ""),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_update",
            "ACTION",
            resource_code=action_code,
            resource_name=action_dict.get("actionName")
            or action_dict.get("action_name", action_code),
            resource_desc=action_dict.get("actionDesc")
            or action_dict.get("action_desc", ""),
            base_code=base_id,
        )
        return action_dict

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Delete an action.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action_code: Target action code.
        """
        _ = object_code  # stored entity keyed by action_code; object_code is context only
        entity_store = self._entity_store.sub_store(base_id)
        entity_store.delete("actions", action_code)
        logger.info(
            "Deleted action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
        )
        self._remove_entity_terms(
            entity_type="ontology_action", entity_code=action_code
        )
        self._invoke_sync_hook(
            "on_delete",
            "ACTION",
            resource_code=action_code,
            base_code=base_id,
        )

    # ── Datasource CRUD ────────────────────────────────────────────────────

    def get_datasources(
        self,
        *,
        base_id: str = "",
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all datasources under a base from the entity store.

        Args:
            base_id: Base / project identifier.
            keyword: Case-insensitive filter on db_id.

        Returns:
            List of Datasource dicts (alias-mapped).
        """
        store = self._entity_store.sub_store(base_id)
        all_ds = store.list_all("datasources")
        if not all_ds:
            return []

        dbs: list[DbConnection] = []
        for ds in all_ds:
            db_list: list[dict[str, Any]] = ds.get("db", [])
            for db_entry in db_list:
                db_id: str = db_entry.get("dbId", db_entry.get("db_id", "")) or ""
                if keyword and keyword.strip().lower() not in db_id.lower():
                    continue
                dbs.append(
                    DbConnection(
                        dbId=db_id,
                        dbCode=db_id,
                        dbType=db_entry.get("dbType", ""),
                        dbParams=db_entry.get("dbParams", {}),
                    )
                )
        if not dbs:
            return []
        return [Datasource(db=dbs).model_dump(by_alias=True)]

    def get_datasource_detail(
        self, db_id: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id from the entity store.

        Args:
            db_id: Database identifier to look up.
            base_id: Base / project identifier.

        Returns:
            Datasource dict if found, otherwise None.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("datasources", db_id)
        if raw is None:
            # Try scanning all datasources for a matching db entry
            all_ds = store.list_all("datasources")
            for ds in all_ds:
                db_list: list[dict[str, Any]] = ds.get("db", [])
                for db_entry in db_list:
                    if db_entry.get("dbId", db_entry.get("db_id", "")) == db_id:
                        raw = ds
                        break
                if raw is not None:
                    break
        if raw is None:
            return None
        db_list = raw.get("db", [])
        dbs: list[DbConnection] = [
            DbConnection(
                dbId=entry.get("dbId", entry.get("db_id", "")),
                dbCode=entry.get("dbCode", entry.get("db_code", entry.get("dbId", ""))),
                dbType=entry.get("dbType", ""),
                dbParams=entry.get("dbParams", {}),
            )
            for entry in db_list
        ]
        return Datasource(db=dbs).model_dump(by_alias=True)

    def create_datasource(self, base_id: str, ds: Any) -> Any:
        """Persist a new datasource via EntityStore.

        Args:
            base_id: Base / project identifier.
            ds: Datasource dict or pydantic model.

        Returns:
            The saved datasource dict.

        Raises:
            ValueError: If db_id is missing or empty.
        """
        entity_store = self._entity_store.sub_store(base_id)
        ds_dict: dict[str, Any] = (
            ds if isinstance(ds, dict) else ds.model_dump(by_alias=True)
        )
        # Datasource wraps a list of DbConnection; extract first db_id
        db_list: list[dict[str, Any]] = ds_dict.get("db", [])
        db_id = ""
        if db_list:
            db_id = db_list[0].get("dbId", db_list[0].get("db_id", ""))
        if not db_id:
            raise ValueError("db_id is required for datasource creation")
        entity_store.save("datasources", db_id, ds_dict)
        logger.info("Created datasource: base_id=%s db_id=%s", base_id, db_id)
        self._invoke_sync_hook(
            "on_create",
            "DATASOURCE",
            resource_code=db_id,
            resource_name=db_id,
            resource_desc="",
            base_code=base_id,
        )
        return ds_dict

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Delete a datasource.

        Args:
            base_id: Base / project identifier.
            db_id: Target database identifier.
        """
        entity_store = self._entity_store.sub_store(base_id)
        entity_store.delete("datasources", db_id)
        logger.info("Deleted datasource: base_id=%s db_id=%s", base_id, db_id)
        self._invoke_sync_hook(
            "on_delete",
            "DATASOURCE",
            resource_code=db_id,
            base_code=base_id,
        )

    # ── Object subtree & base/scene details ───────────────────────────

    def get_object_subtree(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any]:
        """Get a single object's full subtree — detail + related views, relations, actions.

        Args:
            object_code: Target object code.
            base_id: Base identifier.

        Returns:
            Dict with object, views, relations, actions, dbsources.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("objects", object_code)
        if raw is None:
            return {
                "object": None,
                "views": [],
                "relations": [],
                "actions": [],
                "dbsources": {"db": [], "doc": [], "api": []},
            }

        # Object detail
        obj_detail = self.get_object_detail_from_raw(raw, object_code)

        # Views that reference this object
        all_views = store.list_all("views")
        related_views: list[str] = []
        for v in all_views:
            objs = v.get("objects", [])
            for entry in objs:
                obj_code = (
                    entry if isinstance(entry, str) else entry.get("object_code", "")
                )
                if obj_code == object_code:
                    vc = v.get("view_code") or v.get("viewCode") or v.get("view_id", "")
                    if vc:
                        related_views.append(vc)
                    break
        views = self.extract_views_detail(related_views, base_id=base_id)

        # Relations involving this object (bidirectional)
        all_rels = store.list_all("relations")
        relations: list[dict[str, Any]] = []
        for r in all_rels:
            src = r.get("source_class", "")
            tgt = r.get("target_class", "")
            if src != object_code and tgt != object_code:
                continue
            relations.append(self._raw_to_relation_dict(r, store))

        # Actions on this object
        actions = self._raw_actions_to_dicts(raw)

        # Dbsources from object properties
        used_db_ids: set[str] = set()
        if obj_detail:
            for prop in obj_detail.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)
        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(DbConnection(dbId=db_id, dbCode=db_id, dbType="", dbParams={}))

        return {
            "object": obj_detail,
            "views": views,
            "relations": relations,
            "actions": actions,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
        }

    def get_base_details(
        self,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base-level detail — objects, views, relations, actions, dbsources.

        Args:
            base_id: Base / project identifier.
            view_code: Optional view code filter.
            object_code: Optional object code filter.

        Returns:
            Dict with base, scenes, views, objects, actions, relations, dbsources, version.
        """
        store = self._entity_store.sub_store(base_id)
        all_object_codes = [
            r.get("object_code", r.get("objectCode", ""))
            for r in store.list_all("objects")
        ]
        all_view_codes = [
            v.get("view_code", v.get("viewCode", v.get("view_id", "")))
            for v in store.list_all("views")
        ]

        # Filter by view_code / object_code
        if view_code and not object_code:
            target_views = [vc for vc in all_view_codes if vc in set(view_code)]
            target_objects = all_object_codes
        elif object_code and not view_code:
            target_views = []
            target_objects = [oc for oc in all_object_codes if oc in set(object_code)]
        elif view_code and object_code:
            target_views = [vc for vc in all_view_codes if vc in set(view_code)]
            target_objects = list(set(object_code) | set(all_object_codes))
        else:
            target_views = all_view_codes
            target_objects = all_object_codes

        target_obj_set = set(target_objects)

        objects = self.extract_objects_detail(sorted(target_obj_set), base_id=base_id)
        views = self.extract_views_detail(target_views, base_id=base_id)
        relations = self.extract_relations(target_obj_set, base_id=base_id)

        # Extract actions from matching objects
        actions: list[dict[str, Any]] = []
        for code in sorted(target_obj_set):
            raw_obj = store.get("objects", code)
            if raw_obj is not None:
                actions.extend(self._raw_actions_to_dicts(raw_obj))

        # Build dbsources from object properties' dbId
        used_db_ids: set[str] = set()
        for obj_dict in objects:
            for prop in obj_dict.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)
        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(DbConnection(dbId=db_id, dbCode=db_id, dbType="", dbParams={}))

        # Collect all scenes under this base
        scenes_list = self.list_scenes(base_id)  # type: ignore[attr-defined]

        return {
            "base": {"baseId": base_id},
            "scenes": scenes_list,
            "views": views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
            "version": "v0.1.0",
        }

    def get_scene_details(
        self,
        scene_id: str,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get scene details with optional filtering by view_code / object_code.

        Args:
            scene_id: Target scene ID.
            base_id: Base / project identifier.
            view_code: Optional view code filter list.
            object_code: Optional object code filter list.

        Returns:
            Dict with scene, views, objects, actions, relations, dbsources, version.
        """
        member_obj_codes, member_view_codes = self.get_scene_members(base_id, scene_id)  # type: ignore[attr-defined]

        scenes = self._ensure_scenes_loaded()  # type: ignore[attr-defined]
        scene = scenes.get(scene_id)
        if scene is None:
            return {
                "scene": None,
                "views": [],
                "objects": [],
                "actions": [],
                "relations": [],
                "dbsources": Datasource(db=[], doc=[], api=[]).model_dump(
                    by_alias=True
                ),
                "version": "v0.1.0",
            }

        # Determine which objects/views to include based on filter params
        if view_code and not object_code:
            target_views = [vc for vc in member_view_codes if vc in set(view_code)]
            target_objects = member_obj_codes
        elif object_code and not view_code:
            target_views = []
            target_objects = [oc for oc in member_obj_codes if oc in set(object_code)]
        elif view_code and object_code:
            target_views = [vc for vc in member_view_codes if vc in set(view_code)]
            target_objects = list(set(object_code) | set(member_obj_codes))
        else:
            target_views = list(member_view_codes)
            target_objects = list(member_obj_codes)

        target_obj_set = set(target_objects)

        scene_base_id: str = scene.get("base_id", base_id)
        objects = self.extract_objects_detail(
            sorted(target_obj_set), base_id=scene_base_id
        )
        views = self.extract_views_detail(target_views, base_id=base_id)
        relations = self.extract_relations(target_obj_set, base_id=base_id)

        store = self._entity_store.sub_store(scene_base_id)
        actions: list[dict[str, Any]] = []
        for code in sorted(target_obj_set):
            raw_obj = store.get("objects", code)
            if raw_obj is not None:
                actions.extend(self._raw_actions_to_dicts(raw_obj))

        # Build dbsources from object properties' dbId
        used_db_ids: set[str] = set()
        for obj_dict in objects:
            for prop in obj_dict.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)
        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(DbConnection(dbId=db_id, dbCode=db_id, dbType="", dbParams={}))

        return {
            "scene": scene,
            "views": views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
            "version": "v0.1.0",
        }

    # ── Batch ontology extraction helpers ─────────────────────────────

    def _raw_to_object_detail_dict(
        self, raw: dict[str, Any], base_id: str
    ) -> dict[str, Any]:
        """Build ObjectType dict from a raw object dict — no OntologyLoader needed."""
        ext = raw.get("ext_property", {}) or {}
        obj = ObjectType(
            objectCode=raw.get("object_code", raw.get("objectCode", "")),
            objectName=raw.get("object_name", raw.get("objectName", "")),
            objectDesc=raw.get("description") or raw.get("objectDesc"),
            objectSource=raw.get("source_type") or raw.get("sourceType"),
            conceptType=raw.get("concept_type") or raw.get("conceptType"),
            ownerType=ext.get("owner_type")
            or raw.get("owner_type")
            or raw.get("ownerType", "enterprise"),
            userCode=ext.get("user_code")
            or raw.get("user_code")
            or raw.get("userCode"),
            baseId=base_id,
            tableName=raw.get("table_name") or raw.get("tableName"),
            properties=[
                Property(
                    propertyName=f.get("field_name", f.get("fieldName", "")),
                    propertyCode=f.get("field_code", f.get("fieldCode", "")),
                    dataType=f.get("field_type", f.get("fieldType", "STRING")),
                    businessKey=1 if f.get("is_primary_key", False) else 0,
                    sourceColumn=f.get("source_column") or f.get("sourceColumn"),
                    dbId=raw.get("datasource_alias"),
                )
                for f in raw.get("fields", [])
            ],
            actions=[
                Action(
                    actionCode=a.get("action_code", a.get("actionCode", "")),
                    actionName=a.get("action_name", a.get("actionName", "")),
                    actionType=a.get("action_type", a.get("actionType", "")),
                    belongObjectCode=a.get(
                        "belongObjectCode", raw.get("object_code", "")
                    ),
                    actionDesc=a.get("description") or a.get("actionDesc"),
                    requestUrl=a.get("request_url") or a.get("requestUrl"),
                    requestMethod=a.get("request_method") or a.get("requestMethod"),
                    params=[
                        ActionParam(
                            paramCode=p.get("param_code", p.get("paramCode", "")),
                            paramName=p.get("param_name", p.get("paramName", "")),
                            paramType=p.get("param_type") or p.get("paramType"),
                            isRequired=1 if p.get("required", False) else 0,
                            direction=p.get("direction"),
                            mappingPath=p.get("mapping_path") or p.get("mappingPath"),
                        )
                        for p in a.get("params", [])
                    ],
                )
                for a in raw.get("actions", [])
            ],
        )
        return obj.model_dump(by_alias=True)

    def extract_objects_detail(
        self, object_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code from the entity store.

        Args:
            object_codes: Object codes to extract detail for.
            base_id: Base / project identifier.

        Returns:
            List of ObjectType dicts (by_alias=True), without actions in the model
            (actions are included via actions field).
        """
        store = self._entity_store.sub_store(base_id)
        objects: list[dict[str, Any]] = []
        for code in object_codes:
            raw = store.get("objects", code)
            if raw is None:
                continue
            objects.append(self._raw_to_object_detail_dict(raw, base_id))
        return objects

    def extract_views_detail(
        self, view_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code from the entity store.

        Args:
            view_codes: View codes to extract detail for.
            base_id: Base / project identifier.

        Returns:
            List of View dicts (by_alias=True).
        """
        store = self._entity_store.sub_store(base_id)
        views: list[dict[str, Any]] = []
        for vc in view_codes:
            raw = store.get("views", vc)
            if raw is None:
                continue
            views.append(self._raw_to_view_dict(raw, vc))
        return views

    def extract_relations(
        self, object_codes_set: set[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract bidirectional Relation JSON where both ends are in object_codes_set.

        Args:
            object_codes_set: Only relations where both source and target are in this set.
            base_id: Base / project identifier.

        Returns:
            List of Relation dicts (by_alias=True).
        """
        store = self._entity_store.sub_store(base_id)
        all_items = store.list_all("relations")
        relations: list[dict[str, Any]] = []
        for r in all_items:
            rel_dict = self._raw_to_relation_dict(r, store)
            src: str = rel_dict.get("sourceObjectCode", "")
            tgt: str = rel_dict.get("targetObjectCode", "")
            if src not in object_codes_set or tgt not in object_codes_set:
                continue
            relations.append(rel_dict)
        return relations

    def query_ontologies_by_scene(
        self,
        scene_id: str,
        *,
        base_id: str = "",
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        type: str | None = None,
        owner_type: str | None = None,
        user_code: str | None = None,
        cross_scene: bool = False,
    ) -> dict[str, Any]:
        """Query ontologies (objects + views) with pagination, type, and owner_type filters.

        Args:
            scene_id: Target scene ID (empty when cross_scene=True).
            base_id: Base / project identifier.
            page: 1-based page number.
            page_size: Items per page.
            keyword: Case-insensitive filter on name/code.
            type: 'object' or 'view' to restrict to one type.
            owner_type: Filter by owner_type.
            user_code: Filter by user_code.
            cross_scene: If True and scene_id empty, include ALL objects/views.

        Returns:
            Dict with data, totalCount, page, pageSize.
        """
        store = self._entity_store.sub_store(base_id)

        # Determine scope: which object/view codes to include
        obj_codes: list[str] | None = None  # None = all objects
        view_codes: list[str] | None = None  # None = all views

        if not scene_id and cross_scene:
            # Cross-scene: no code restriction
            pass  # obj_codes/view_codes stay None
        else:
            scenes = self._ensure_scenes_loaded()  # type: ignore[attr-defined]
            found = scenes.get(scene_id)
            if found is None:
                return {
                    "data": {"objects": [], "views": []},
                    "totalCount": 0,
                    "page": page,
                    "pageSize": page_size,
                }
            # Non-empty filter: only query codes that belong to this scene.
            # An empty filter means the scene has no members — return empty.
            obj_members: list[str] = list(found.get("member_object_codes", []))
            vw_members: list[str] = list(found.get("member_view_codes", []))
            if not obj_members and not vw_members:
                return {
                    "data": {"objects": [], "views": []},
                    "totalCount": 0,
                    "page": page,
                    "pageSize": page_size,
                }
            obj_codes = obj_members
            view_codes = vw_members

        # Batch query objects via store.search (keyword filtered at DB level)
        # Load in batches, post-filter owner/user, stop when enough for requested page.
        fetch_size = max(
            page_size * 4, 500
        )  # Load extra to account for owner/user filtering
        all_objects: list[dict[str, Any]] = []
        obj_total = 0
        obj_page = 1
        if type is None or type.lower() != "view":
            while True:
                obj_items, _t = store.search(
                    "objects",
                    keyword=keyword,
                    codes=obj_codes,
                    page=obj_page,
                    page_size=fetch_size,
                )
                obj_total = _t  # Total matching objects (before owner/user filter)
                for raw in obj_items:
                    summary = self._raw_to_summary(raw)
                    if owner_type and summary.owner_type != owner_type:
                        continue
                    if user_code and summary.user_code != user_code:
                        continue
                    all_objects.append(
                        {
                            "objectCode": summary.object_code,
                            "objectName": summary.object_name,
                            "objectDesc": summary.description,
                            "objectSource": summary.object_source,
                            "fieldCount": summary.field_count,
                            "actionCount": summary.action_count,
                            "ownerType": summary.owner_type,
                            "userCode": summary.user_code,
                        }
                    )
                # Stop if: batch was partial (end of data) OR we have enough for page
                if len(obj_items) < fetch_size:
                    break
                if len(all_objects) >= page * page_size:
                    break
                obj_page += 1

        # Batch query views via store.search (keyword filtered at DB level)
        all_views: list[dict[str, Any]] = []
        vw_total = 0
        vw_page = 1
        if type is None or type.lower() != "object":
            while True:
                vw_items, _t = store.search(
                    "views",
                    keyword=keyword,
                    codes=view_codes,
                    page=vw_page,
                    page_size=fetch_size,
                )
                vw_total = _t
                for raw in vw_items:
                    vc = raw.get(
                        "view_code", raw.get("viewCode", raw.get("view_id", ""))
                    )
                    view_summary = self._to_view_summary(raw, vc)
                    if owner_type and view_summary.owner_type != owner_type:
                        continue
                    if user_code and view_summary.user_code != user_code:
                        continue
                    all_views.append(
                        {
                            "viewCode": view_summary.view_code,
                            "viewName": view_summary.view_name,
                            "description": view_summary.description,
                            "objectCodes": view_summary.object_codes,
                            "ownerType": view_summary.owner_type,
                            "userCode": view_summary.user_code,
                        }
                    )
                if len(vw_items) < fetch_size:
                    break
                if len(all_objects) + len(all_views) >= page * page_size:
                    break
                vw_page += 1

        # Pagination (client-side after owner/user post-filter)
        total = obj_total + vw_total  # Pre-filter total from store
        offset = (page - 1) * page_size
        paged_objects = all_objects[offset : offset + page_size]
        remaining = page_size - len(paged_objects)
        paged_views: list[dict[str, Any]] = []
        if remaining > 0:
            view_start = max(0, offset - len(all_objects))
            paged_views = all_views[view_start : view_start + remaining]

        return {
            "data": {"objects": paged_objects, "views": paged_views},
            "totalCount": total,
            "page": page,
            "pageSize": page_size,
        }

    # ── Property name/code resolution ────────────────────────────────

    def resolve_property_name(
        self, name_text: str, scope_code: str, *, base_id: str = ""
    ) -> tuple[str, str] | None:
        """Resolve a single Chinese property name to (field_code, field_name).

        Iterates the object's fields from the entity store, matching field_name
        or aliases.

        Args:
            name_text: The property name text to resolve.
            scope_code: The object code whose fields to search.
            base_id: Base / project identifier.

        Returns:
            (field_code, field_name) or None if not found.
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("objects", scope_code)
        if raw is None:
            return None
        for f in raw.get("fields", []):
            field_name: str = f.get("field_name", f.get("fieldName", "")) or ""
            field_code: str = f.get("field_code", f.get("fieldCode", "")) or ""
            aliases: list[str] = list(f.get("aliases", []) or [])
            if (
                name_text == field_name
                or name_text in aliases
                or name_text == field_code
            ):
                return (field_code, field_name)
        return None

    def resolve_property_names(
        self, name_texts: list[str], scope_code: str, *, base_id: str = ""
    ) -> dict[str, tuple[str, str]]:
        """Batch resolve property names. Only returns successfully resolved entries.

        Args:
            name_texts: List of property name texts to resolve.
            scope_code: The object code whose fields to search.
            base_id: Base / project identifier.

        Returns:
            Dict of {name_text: (field_code, field_name)} for resolved names.
        """
        result: dict[str, tuple[str, str]] = {}
        for name_text in name_texts:
            resolved = self.resolve_property_name(
                name_text, scope_code, base_id=base_id
            )
            if resolved is not None:
                result[name_text] = resolved
        return result

    def get_property_aliases(
        self, field_code: str, scope_code: str, *, base_id: str = ""
    ) -> list[str]:
        """Get all aliases (including field_name) for a field_code.

        Args:
            field_code: The field code to look up.
            scope_code: The object code whose fields to search.
            base_id: Base / project identifier.

        Returns:
            List of alias strings (including the primary field_name).
        """
        store = self._entity_store.sub_store(base_id)
        raw = store.get("objects", scope_code)
        if raw is None:
            return []
        for f in raw.get("fields", []):
            fc = f.get("field_code", f.get("fieldCode", "")) or ""
            if fc == field_code:
                result: list[str] = [f.get("field_name", f.get("fieldName", "")) or ""]
                result.extend(f.get("aliases", []) or [])
                return result
        return []

    # ── View / joinkey related-object resolution ─────────────────────

    def get_view_included_objects(
        self, ontology_code: str, *, base_id: str = ""
    ) -> list[str]:
        """Return object codes that the view includes (via HAS_OBJECT/MANY_TO_ONE relations).

        Args:
            ontology_code: The view code to query.
            base_id: Base / project identifier.

        Returns:
            List of target object codes.
        """
        store = self._entity_store.sub_store(base_id)
        all_rels = store.list_all("relations")
        result: list[str] = []
        for r in all_rels:
            source = r.get("source_class", r.get("source_object_code", "")) or ""
            category = r.get("relation_category", "") or ""
            if source != ontology_code:
                continue
            if category not in ("HAS_OBJECT", "MANY_TO_ONE"):
                continue
            target = r.get("target_class", r.get("target_object_code", "")) or ""
            if target and target not in result:
                result.append(target)
        return result

    def get_joinkey_related_objects(
        self,
        ontology_code: str,
        field_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[str]:
        """Return object codes related via join keys matching field_codes.

        Args:
            ontology_code: The object code whose relations to query.
            field_codes: Field codes to match against join key source fields.
            base_id: Base / project identifier.

        Returns:
            List of target object codes with matching join keys.
        """
        if not field_codes:
            return []
        field_set = frozenset(field_codes)
        store = self._entity_store.sub_store(base_id)
        all_rels = store.list_all("relations")
        result: list[str] = []
        for r in all_rels:
            source = r.get("source_class", r.get("source_object_code", "")) or ""
            category = r.get("relation_category", "") or ""
            if source != ontology_code:
                continue
            if category not in ("HAS_OBJECT", "MANY_TO_ONE"):
                continue
            ext_attrs = r.get("ext_attrs", {}) or {}
            jks = ext_attrs.get("joinkeys") or []
            if not jks:
                continue
            for jk in jks:
                if isinstance(jk, dict) and jk.get("sourceField") in field_set:
                    target = (
                        r.get("target_class", r.get("target_object_code", "")) or ""
                    )
                    if target and target not in result:
                        result.append(target)
                    break
        return result

    # ── Property term bindings ───────────────────────────────────────

    def get_object_property_term_bindings(
        self,
        object_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query property-level terminology bindings from object fields.

        Args:
            object_codes: Object codes to query.
            base_id: Base / project identifier.
            term_master_type: Optional term master type filter.
            property_codes: Optional property code whitelist.

        Returns:
            List of binding dicts with objectCode, objectName, propertyCode,
            propertyName, dataType, bindingType.
        """
        _ = term_master_type
        store = self._entity_store.sub_store(base_id)
        result: list[dict[str, Any]] = []
        for code in object_codes:
            raw = store.get("objects", code)
            if raw is None:
                continue
            obj_name = raw.get("object_name", raw.get("objectName", "")) or ""
            for f in raw.get("fields", []):
                prop_code = f.get("field_code", f.get("fieldCode", "")) or ""
                if not prop_code:
                    continue
                if property_codes and prop_code not in property_codes:
                    continue
                prop_name = f.get("field_name", f.get("fieldName", "")) or ""
                result.append(
                    {
                        "objectCode": code,
                        "objectName": obj_name,
                        "propertyCode": prop_code,
                        "propertyName": prop_name,
                        "dataType": f.get("field_type", f.get("fieldType", "")),
                        "bindingType": "property",
                    }
                )
        return result

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query property-level terminology bindings from view mappings.

        Args:
            view_codes: View codes to query.
            base_id: Base / project identifier.
            term_master_type: Optional term master type filter.
            property_codes: Optional property code whitelist.

        Returns:
            List of binding dicts with objectCode, objectName, propertyCode,
            propertyName, bindingType.
        """
        _ = term_master_type
        store = self._entity_store.sub_store(base_id)
        result: list[dict[str, Any]] = []
        for vc in view_codes:
            raw = store.get("views", vc)
            if raw is None:
                continue
            for m in raw.get("mappings", []):
                prop_code = m.get("property_code", "")
                src_obj_code = m.get("source_object_code", "")
                src_col_code = m.get("source_object_column_code", "")
                if not prop_code:
                    continue
                if property_codes and prop_code not in property_codes:
                    continue
                src_obj = store.get("objects", src_obj_code)
                src_obj_name = (
                    src_obj.get("object_name", src_obj.get("objectName", src_obj_code))
                    if src_obj
                    else src_obj_code
                ) or ""
                result.append(
                    {
                        "viewCode": vc,
                        "viewName": raw.get("view_name", ""),
                        "propertyCode": prop_code,
                        "propertyName": m.get("property_name", ""),
                        "sourceObjectCode": src_obj_code,
                        "sourceObjectName": src_obj_name,
                        "sourceColumnCode": src_col_code,
                        "bindingType": "view_property",
                    }
                )
        return result

    # ── Term sync helpers (called by CRUD methods) ─────────────────────────

    @staticmethod
    def _normalize_entity_keys(
        entities: list[dict[str, Any]], mapping: dict[str, str]
    ) -> None:
        """Copy legacy camelCase keys to snake_case for entities that lack them.

        Mutates *entities* in-place — only sets a key when the snake_case key
        is missing and the camelCase key exists (no overwrite).
        """
        for entity in entities:
            for camel, snake in mapping.items():
                if snake not in entity and camel in entity:
                    entity[snake] = entity[camel]

    @staticmethod
    def _extract_fields_from_entity(
        entity_type: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract field dicts for term sync, typed by entity kind."""
        if entity_type == "object":
            raw_props: list[dict[str, Any]] = data.get("properties", []) or []
            return [
                {
                    "property_code": (
                        p.get("propertyCode") or p.get("property_code", "")
                    ),
                    "property_name": (
                        p.get("propertyName") or p.get("property_name", "")
                    ),
                    "data_type": p.get("dataType", "STRING"),
                }
                for p in raw_props
            ]
        if entity_type == "view":
            raw_mappings: list[dict[str, Any]] = (
                data.get("properties") or data.get("mappings") or []
            )
            return [
                {
                    "property_code": (
                        m.get("propertyCode") or m.get("property_code", "")
                    ),
                    "property_name": (
                        m.get("propertyName") or m.get("property_name", "")
                    ),
                }
                for m in raw_mappings
            ]
        if entity_type == "action":
            raw_params: list[dict[str, Any]] = data.get("params", []) or []
            return [
                {
                    "property_code": (p.get("paramCode") or p.get("param_code", "")),
                    "property_name": (p.get("paramName") or p.get("param_name", "")),
                }
                for p in raw_params
            ]
        # relation — no sub-fields
        return []

    # ── Term type mapping (entity_type → knowledge DB term_type_code) ───
    _TERM_TYPE_MAP: dict[str, str] = {
        "object": "object",
        "view": "view",
        "relation": "relation",
        "action": "ontology_action",
    }

    @staticmethod
    def _batch_sync_entity_terms(
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> None:
        """Batch-upsert entity terms with single-SQL bulk INSERT ON CONFLICT.

        1. Collects entity tuples from the input lists (fast, no I/O).
        2. **Synchronous**: bulk-upsert all terms → bulk-upsert all term_names
           in a single DB session (one writer, two SQLs).
        3. **Asynchronous**: spawns a daemon thread for tsvector + embedding
           backfill.

        Failures are logged but do not block the import.
        """
        entities: list[tuple[str, str, str]] = []
        for obj in objects:
            code = obj.get("object_code", "")
            name = obj.get("object_name", "")
            if code and name:
                entities.append(("object", code, name))
            # Collect object property terms (fields)
            for field in obj.get("fields", []):
                prop_code = field.get("field_code", field.get("fieldCode", "")) or ""
                prop_name = field.get("field_name", field.get("fieldName", "")) or ""
                if prop_code and prop_name:
                    entities.append(("prop", f"o.{code}.{prop_code}", prop_name))
        for view in views:
            code = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            name = view.get("view_name", "")
            if code and name:
                entities.append(("view", code, name))
            # Collect view property terms (mappings)
            for mapping in view.get("mappings", []):
                prop_code = mapping.get("property_code", "") or ""
                prop_name = mapping.get("property_name", "") or ""
                if prop_code and prop_name:
                    entities.append(("prop", f"v.{code}.{prop_code}", prop_name))
        for rel in relations:
            code = rel.get("relation_code", rel.get("relationCode", "")) or ""
            name = rel.get("relation_name", "")
            if code and name:
                entities.append(("relation", code, name))
        for act in actions:
            code = act.get("action_code", act.get("actionCode", "")) or ""
            name = act.get("action_name", "")
            if code and name:
                entities.append(("action", code, name))

        if not entities:
            return

        term_type_map = {
            "object": "object",
            "view": "view",
            "relation": "relation",
            "action": "ontology_action",
            "prop": "prop",
        }

        terms: list[tuple[str, str, str]] = [
            (code, name, term_type_map[entity_type])
            for entity_type, code, name in entities
        ]
        term_ids: list[str] = []

        # ── 1. 同步：单次批量 UPSERT term + term_name ──
        try:
            from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

            with create_writer() as writer:
                term_ids = writer.bulk_upsert_terms_no_library(terms=terms)
                if term_ids:
                    writer.bulk_create_term_names_no_scope(
                        items=[
                            (tid, name) for tid, (_, name, _) in zip(term_ids, terms)
                        ]
                    )
        except ImportError:
            logger.debug(
                "_batch_sync_entity_terms skipped (datacloud_knowledge unavailable)"
            )
            return
        except Exception:
            logger.exception("_batch_sync_entity_terms: bulk upsert failed")
            return

        logger.info("_batch_sync_entity_terms: upserted %d terms", len(term_ids))

        if not term_ids:
            return

        # ── 2. 异步：向量回填 ──
        def _backfill() -> None:
            try:
                from datacloud_knowledge.adapters import (  # noqa: PLC0415
                    backfill_embeddings,
                    backfill_tsvector,
                )

                backfill_tsvector()
            except Exception:
                logger.exception("_batch_sync_entity_terms: tsvector backfill failed")
            try:
                backfill_embeddings(term_ids=term_ids, batch_size=50)
            except Exception:
                logger.exception("_batch_sync_entity_terms: embeddings backfill failed")

        import threading

        threading.Thread(target=_backfill, daemon=True).start()

    def _sync_entity_terms(
        self,
        *,
        entity_type: str,
        entity_code: str,
        entity_name: str,
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        base_id: str = "",
        domain_codes: tuple[str, ...] | None = None,
    ) -> None:
        """Write entity term into knowledge DB via ``create_writer``.

        Calls ``upsert_term`` with ``backfill_vectors=False`` — vector
        backfill runs in a daemon thread after commit (best-effort,
        non-blocking, failure logged).

        When ``fields`` is provided, also upserts property terms with
        ``o.{entity_code}.{field_code}`` (object) or ``v.{entity_code}.{property_code}``
        (view) prefix format.
        """
        try:
            from datacloud_knowledge.adapters import (  # noqa: PLC0415
                backfill_embeddings,
                create_writer,
            )

            term_type_code = self._TERM_TYPE_MAP.get(entity_type, entity_type)
            domains = list(domain_codes) if domain_codes else []

            with create_writer() as writer:
                # Upsert property terms first (if fields provided)
                prop_term_ids: list[str] = []
                if fields:
                    for field in fields:
                        if entity_type == "object":
                            fc = (
                                field.get("field_code", field.get("fieldCode", ""))
                                or ""
                            )
                            fn = (
                                field.get("field_name", field.get("fieldName", ""))
                                or ""
                            )
                            if fc and fn:
                                prop_term_id = writer.upsert_term(
                                    term_code=f"o.{entity_code}.{fc}",
                                    term_name=fn,
                                    term_type_code="prop",
                                    library_id=base_id or None,
                                    domain_ids=domains,
                                    search_scope={"base": base_id} if base_id else {},
                                    backfill_vectors=False,
                                )
                                if prop_term_id:
                                    prop_term_ids.append(prop_term_id)
                        elif entity_type == "view":
                            pc = (
                                field.get(
                                    "property_code", field.get("propertyCode", "")
                                )
                                or ""
                            )
                            pn = (
                                field.get(
                                    "property_name", field.get("propertyName", "")
                                )
                                or ""
                            )
                            if pc and pn:
                                prop_term_id = writer.upsert_term(
                                    term_code=f"v.{entity_code}.{pc}",
                                    term_name=pn,
                                    term_type_code="prop",
                                    library_id=base_id or None,
                                    domain_ids=domains,
                                    search_scope={"base": base_id} if base_id else {},
                                    backfill_vectors=False,
                                )
                                if prop_term_id:
                                    prop_term_ids.append(prop_term_id)

                term_id = writer.upsert_term(
                    term_code=entity_code,
                    term_name=entity_name,
                    term_type_code=term_type_code,
                    library_id=base_id or None,
                    domain_ids=domains,
                    search_scope={"base": base_id} if base_id else {},
                    backfill_vectors=False,
                )

            logger.info(
                "_sync_entity_terms: type=%s term_type=%s code=%s done",
                entity_type,
                term_type_code,
                entity_code,
            )

            # Defer vector backfill to daemon thread — non-blocking
            all_term_ids: list[str] = []
            if term_id:
                all_term_ids.append(term_id)
            all_term_ids.extend(prop_term_ids)
            if all_term_ids:
                import threading

                def _backfill() -> None:
                    try:
                        backfill_embeddings(term_ids=all_term_ids, batch_size=50)
                    except Exception:
                        logger.exception(
                            "_sync_entity_terms: embedding backfill failed "
                            "type=%s code=%s term_ids=%s",
                            entity_type,
                            entity_code,
                            all_term_ids,
                        )

                threading.Thread(target=_backfill, daemon=True).start()
        except ImportError:
            logger.debug(
                "_sync_entity_terms skipped (datacloud_knowledge unavailable): "
                "type=%s code=%s",
                entity_type,
                entity_code,
            )
        except Exception:
            logger.exception(
                "_sync_entity_terms failed: type=%s code=%s", entity_type, entity_code
            )

    def _remove_entity_terms(self, *, entity_type: str, entity_code: str) -> None:
        """Remove entity terms from knowledge DB on delete/update.

        Uses the standalone ``delete_scope`` function (reader/writer
        agnostic) for cascading delete of term + name + relation + knowledge.
        """
        try:
            from datacloud_knowledge.adapters import delete_scope  # noqa: PLC0415

            scope = f"{entity_type}:{entity_code}"
            delete_scope(scope)
            logger.info(
                "_remove_entity_terms: type=%s code=%s done", entity_type, entity_code
            )
        except ImportError:
            logger.debug(
                "_remove_entity_terms skipped (datacloud_knowledge unavailable): "
                "type=%s code=%s",
                entity_type,
                entity_code,
            )
        except Exception:
            logger.exception(
                "_remove_entity_terms failed: type=%s code=%s",
                entity_type,
                entity_code,
            )

    def _sync_entity_domains(
        self,
        base_id: str,
        scene_id: str,
        entity_type: str,
        entity_codes: list[str],
    ) -> None:
        """Called by add_scene_members — merges scene_id into term.domain_ids.

        Batch-reads all existing terms by ``term_code = entity_code`` in one
        DB query, then merges ``scene_id`` into each term's domain_ids set
        and writes back via ``update_term``.  Existing scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            # Batch-read all terms in a single DB query (was O(N) per-entity).
            terms_batch = reader.get_terms_batch_raw(term_codes=entity_codes)  # type: ignore[attr-defined]
            term_map: dict[str, dict[str, object]] = {
                str(t["term_code"]): t for t in terms_batch if t.get("term_code")
            }

            missing = [c for c in entity_codes if c not in term_map]
            if missing:
                logger.warning(
                    "_sync_entity_domains: %d terms not found (e.g. %s)",
                    len(missing),
                    ", ".join(missing[:5]),
                )

            if not term_map:
                return

            with create_writer() as writer:
                for entity_code, term_data in term_map.items():
                    try:
                        term_id = str(term_data.get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = (
                            cast("list[str]", term_data.get("domain_ids")) or []
                        )
                        merged = list({*current_domains, scene_id})
                        writer.update_term(
                            dataset_id=base_id,
                            term_id=term_id,
                            updates=TermUpdate(domain_ids=merged),
                        )
                        logger.info(
                            "_sync_entity_domains: type=%s code=%s scene=%s domains=%s done",
                            entity_type,
                            entity_code,
                            scene_id,
                            merged,
                        )
                    except Exception:
                        logger.exception(
                            "_sync_entity_domains: failed for code=%s, "
                            "rolling back entire batch",
                            entity_code,
                        )
                        raise
                # commit handled by context manager exit
        except ImportError:
            logger.debug(
                "_sync_entity_domains skipped (datacloud_knowledge unavailable)"
            )
        except Exception:
            logger.exception(
                "_sync_entity_domains failed: type=%s scene=%s",
                entity_type,
                scene_id,
            )

    def _remove_entity_domains(
        self,
        base_id: str,
        scene_id: str,
        entity_type: str,
        entity_codes: list[str],
    ) -> None:
        """Called by remove_scene_members — removes scene_id from term.domain_ids.

        Batch-reads all existing terms by ``term_code = entity_code`` in one
        DB query, then removes ``scene_id`` from each term's domain_ids set
        and writes back via ``update_term``.  Other scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            # Batch-read all terms in a single DB query (was O(N) per-entity).
            terms_batch = reader.get_terms_batch_raw(term_codes=entity_codes)  # type: ignore[attr-defined]
            term_map: dict[str, dict[str, object]] = {
                str(t["term_code"]): t for t in terms_batch if t.get("term_code")
            }

            missing = [c for c in entity_codes if c not in term_map]
            if missing:
                logger.warning(
                    "_remove_entity_domains: %d terms not found (e.g. %s)",
                    len(missing),
                    ", ".join(missing[:5]),
                )

            if not term_map:
                return

            with create_writer() as writer:
                for entity_code, term_data in term_map.items():
                    try:
                        term_id = str(term_data.get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = (
                            cast("list[str]", term_data.get("domain_ids")) or []
                        )
                        updated = [d for d in current_domains if d != scene_id]
                        writer.update_term(
                            dataset_id=base_id,
                            term_id=term_id,
                            updates=TermUpdate(domain_ids=updated),
                        )
                        logger.info(
                            "_remove_entity_domains: type=%s code=%s scene=%s domains=%s done",
                            entity_type,
                            entity_code,
                            scene_id,
                            updated,
                        )
                    except Exception:
                        logger.exception(
                            "_remove_entity_domains: failed for code=%s, "
                            "rolling back entire batch",
                            entity_code,
                        )
                        raise
                # commit handled by context manager exit
        except ImportError:
            logger.debug(
                "_remove_entity_domains skipped (datacloud_knowledge unavailable)"
            )
        except Exception:
            logger.exception(
                "_remove_entity_domains failed: type=%s scene=%s",
                entity_type,
                scene_id,
            )
