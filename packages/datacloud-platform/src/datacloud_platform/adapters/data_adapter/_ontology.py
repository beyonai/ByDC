"""OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.adapters.data_adapter._base import (
    DataCloudDataBackendBase,
    _normalize_object_codes,
)
from datacloud_platform.models import ObjectSummary, ParsedOwlContent
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)


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
        entity_store = self._entity_store.sub_store(base_path.name)

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
        self._batch_sync_entity_terms(objects, views, relations, actions)

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

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load ontology from EntityStore into a queryable runtime object.

        Reads all entity types from the store and assembles an OntologyLoader.
        Falls back to OWL parsing when the store has no data for this base.

        Args:
            base_path: Path to the OWL resource directory root
                       (used for OWL fallback and store namespace derivation).

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        base_id = base_path.name
        store = self._entity_store.sub_store(base_id)

        # Build registry-like content from store
        all_objects = [
            store.get("objects", code) for code in store.load_index("objects")
        ]
        all_objects = [o for o in all_objects if o]
        all_views = [store.get("views", code) for code in store.load_index("views")]
        all_views = [v for v in all_views if v]
        all_relations = [
            store.get("relations", code) for code in store.load_index("relations")
        ]
        all_relations = [r for r in all_relations if r]
        all_actions = [
            store.get("actions", code) for code in store.load_index("actions")
        ]
        all_actions = [a for a in all_actions if a]
        all_dbsources = [
            store.get("datasources", db_id) for db_id in store.load_index("datasources")
        ]
        all_dbsources = [d for d in all_dbsources if d]

        if any([all_objects, all_views, all_relations, all_actions, all_dbsources]):
            # Normalize legacy camelCase keys to snake_case for all entity types.
            # Filtered lists contain no None at runtime (see [a for a in ... if a] above),
            # but mypy cannot narrow through list comprehension reassignment.
            _obj_map = {"objectCode": "object_code"}
            _view_map = {"viewCode": "view_code", "viewId": "view_code"}
            _rel_map = {"relationCode": "relation_code"}
            _act_map = {"actionCode": "action_code"}
            self._normalize_entity_keys(all_objects, _obj_map)  # type: ignore[arg-type]
            self._normalize_entity_keys(all_views, _view_map)  # type: ignore[arg-type]
            self._normalize_entity_keys(all_relations, _rel_map)  # type: ignore[arg-type]
            self._normalize_entity_keys(all_actions, _act_map)  # type: ignore[arg-type]

            # OntologyLoader uses view["view_id"] as the dict key (line 365/434),
            # but normalization only sets view_code.  Mirror view_code → view_id
            # so loader._views keys match get_view_detail() lookups.
            for v in all_views:
                if v is not None and "view_id" not in v:
                    v["view_id"] = v.get("view_code", "")

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
            return loader  # type: ignore[return-value]

        # Fallback: OWL directory exists but store is empty
        if base_path.exists():
            logger.info(
                "Store empty for base_id=%s, falling back to parse_owl + batch_import_ontology",
                base_id,
            )
            parsed = self.parse_owl(base_path)
            self.batch_import_ontology(
                base_path,
                parsed.objects,
                parsed.views,
                parsed.relations,
                parsed.actions,
                parsed.dbsources,
            )
            return self.load_ontology(base_path)  # recurse → store now has data

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
        loader: OntologyQueryable,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[ObjectSummary]:
        """Get all object summaries under a base with optional filtering.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.
            owner_type: Filter by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on name/code/description.

        Returns:
            List of ObjectSummary for matching classes.
        """
        _ = base_id
        result: list[ObjectSummary] = []
        for cls in loader._classes.values():
            ext = getattr(cls, "ext_property", None) or {}
            cls_owner: str = ext.get("owner_type", "enterprise")
            if owner_type and cls_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                cls_user: str | None = ext.get("user_code")
                if cls_user != user_code:
                    continue
            summary = self._to_summary(cls)
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in (summary.object_name or "").lower()
                    and kw not in summary.object_code.lower()
                    and kw not in (summary.description or "").lower()
                ):
                    continue
            result.append(summary)
        return result

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> dict[str, Any] | None:
        """Get full object detail with properties and actions.

        Args:
            loader: An OntologyQueryable with _classes populated.
            object_code: The object code to look up.

        Returns:
            Full ObjectType dict (alias-mapped) if found, otherwise None.
        """
        cls = loader._classes.get(object_code)
        if cls is None:
            return None
        obj = ObjectType(
            objectCode=cls.object_code,
            objectName=cls.object_name,
            objectDesc=getattr(cls, "description", None),
            objectSource=getattr(cls, "source_type", None),
            conceptType=getattr(cls, "concept_type", None),
            ownerType=getattr(cls, "owner_type", "enterprise"),
            userCode=getattr(cls, "user_code", None),
            baseId="",
            properties=[
                Property(
                    propertyName=f.field_name,
                    propertyCode=f.field_code,
                    dataType=f.field_type,
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
        entity_store.save("objects", code, obj_dict)
        logger.info("Created object: base_id=%s object_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="object",
            entity_code=code,
            entity_name=obj_dict.get("objectName") or obj_dict.get("object_name", code),
            entity_desc=obj_dict.get("objectDesc") or obj_dict.get("description", ""),
            base_id=base_id,
        )
        self._invoke_sync_hook(
            "on_create",
            "OBJECT",
            resource_code=code,
            resource_name=obj_dict.get("objectName")
            or obj_dict.get("object_name", code),
            resource_desc=obj_dict.get("objectDesc") or obj_dict.get("object_desc", ""),
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

    def get_views(
        self,
        loader: Any,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all views from the loaded ontology with optional filtering.

        Args:
            loader: An OntologyQueryable with _views populated.
            base_id: Base / project identifier.
            owner_type: Filter by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on view_name/view_code/description.

        Returns:
            List of View dicts (alias-mapped).
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        result: list[dict[str, Any]] = []
        for vc, view_data in raw_views.items():
            # owner_type filter — read from ext_property first, fall back to top-level
            ext = view_data.get("ext_property", {}) or {}
            v_owner: str = (
                ext.get(
                    "owner_type",
                    view_data.get(
                        "owner_type", view_data.get("ownerType", "enterprise")
                    ),
                )
                or "enterprise"
            )
            if owner_type and v_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                v_user: str | None = view_data.get("user_code") or view_data.get(
                    "userCode"
                )
                if v_user != user_code:
                    continue
            normalized_codes = _normalize_object_codes(view_data.get("objects", []))
            view = View(
                viewCode=view_data.get("view_id", vc),
                viewName=view_data.get("view_name", ""),
                description=view_data.get("description"),
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
                    for m in view_data.get("mappings", [])
                ],
            )
            view_dict = view.model_dump(by_alias=True)
            # keyword filter
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in (view_dict.get("viewName", "") or "").lower()
                    and kw not in (view_dict.get("viewCode", "") or "").lower()
                    and kw not in (view_dict.get("description", "") or "").lower()
                ):
                    continue
            result.append(view_dict)
        return result

    def get_view_detail(
        self, loader: Any, base_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Get single view detail by code from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _views populated.
            base_id: Base / project identifier.
            view_code: View identifier to look up.

        Returns:
            View dict if found, otherwise None.
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        view_data = raw_views.get(view_code)
        if view_data is None:
            return None
        normalized_codes = _normalize_object_codes(view_data.get("objects", []))
        view = View(
            viewCode=view_data.get("view_id", view_code),
            viewName=view_data.get("view_name", ""),
            description=view_data.get("description"),
            objectCodes=normalized_codes,
            ownerType=view_data.get(
                "owner_type", view_data.get("ownerType", "enterprise")
            ),
            userCode=view_data.get("user_code", view_data.get("userCode")),
            properties=[
                ViewProperty(
                    propertyName=m.get("property_name", ""),
                    propertyCode=m.get("property_code", ""),
                    sourceObject=m.get("source_object_code", ""),
                    sourceObjectProperty=m.get("source_object_column_code", ""),
                )
                for m in view_data.get("mappings", [])
            ],
        )
        return view.model_dump(by_alias=True)

    def get_objects_by_view(
        self,
        loader: Any,
        base_id: str,
        view_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get object summaries (code/name/description) referenced by a view.

        Supports owner_type/user_code/keyword filtering.

        Args:
            loader: An OntologyQueryable with _views and _classes populated.
            base_id: Base / project identifier.
            view_code: View code to look up.
            owner_type: Filter objects by owner_type (enterprise/personal).
            user_code: Filter by user_code when owner_type is personal.
            keyword: Case-insensitive filter on object_name/object_code/description.

        Returns:
            List of object dicts with objectCode/objectName/objectDesc/ownerType/userCode.
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        view_data = raw_views.get(view_code)
        if view_data is None:
            return []

        normalized_codes = _normalize_object_codes(view_data.get("objects", []))
        result: list[dict[str, Any]] = []
        for code in normalized_codes:
            cls = loader._classes.get(code)
            if cls is None:
                continue
            ext = getattr(cls, "ext_property", None) or {}
            cls_owner: str = ext.get("owner_type", "enterprise")
            if owner_type and cls_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                cls_user: str | None = ext.get("user_code")
                if cls_user != user_code:
                    continue
            obj_dict: dict[str, Any] = {
                "objectCode": cls.object_code,
                "objectName": cls.object_name,
                "objectDesc": getattr(cls, "description", ""),
                "ownerType": cls_owner,
                "userCode": getattr(cls, "user_code", None),
            }
            if keyword:
                kw = keyword.strip().lower()
                if (
                    kw not in (cls.object_name or "").lower()
                    and kw not in cls.object_code.lower()
                    and kw not in (getattr(cls, "description", "") or "").lower()
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
        entity_store.save("views", code, view_dict)
        logger.info("Created view: base_id=%s view_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=code,
            entity_name=view_dict.get("viewName") or view_dict.get("view_name", code),
            entity_desc=view_dict.get("description", ""),
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
        entity_store.save("views", view_code, view_dict)
        logger.info("Updated view: base_id=%s view_code=%s", base_id, view_code)
        self._remove_entity_terms(entity_type="view", entity_code=view_code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=view_code,
            entity_name=view_dict.get("viewName")
            or view_dict.get("view_name", view_code),
            entity_desc=view_dict.get("description", ""),
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

    # ── Relation CRUD (stub — datacloud-data SDK does not yet support) ──────

    def get_relations(
        self,
        loader: Any,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relations from the loaded ontology.

        Supports both OntologyRelation objects and raw dicts.
        Resolves sourceObjectName / targetObjectName from loader._classes.
        """
        raw_relations: list[Any] = getattr(loader, "_relations", None) or []
        result: list[dict[str, Any]] = []
        for r in raw_relations:
            if hasattr(r, "source_class"):
                src = r.source_class
                tgt = r.target_class
            elif isinstance(r, dict):
                src = r.get("source_class", "")
                tgt = r.get("target_class", "")
            else:
                continue
            src_name = ""
            tgt_name = ""
            src_cls = loader._classes.get(src)
            if src_cls is not None:
                src_name = src_cls.object_name
            tgt_cls = loader._classes.get(tgt)
            if tgt_cls is not None:
                tgt_name = tgt_cls.object_name

            if hasattr(r, "relation_code"):
                rel = Relation(
                    relationCode=r.relation_code,
                    relationName=getattr(r, "relation_name", None),
                    sourceObjectCode=src,
                    targetObjectCode=tgt,
                    relationCardinality=getattr(r, "relation_type", None),
                    sourceObjectName=src_name,
                    targetObjectName=tgt_name,
                    relationDesc=getattr(r, "relation_desc", None)
                    or getattr(r, "description", None),
                    relationSceneType=getattr(r, "relation_scene_type", None),
                    ownerType=getattr(r, "owner_type", "enterprise"),
                    userCode=getattr(r, "user_code", None),
                )
            elif isinstance(r, dict):
                rel = Relation(
                    relationCode=r.get("relation_code", ""),
                    relationName=r.get("relation_name"),
                    sourceObjectCode=src,
                    targetObjectCode=tgt,
                    relationCardinality=r.get("relation_type"),
                    sourceObjectName=src_name,
                    targetObjectName=tgt_name,
                    relationDesc=r.get("relation_desc") or r.get("description"),
                    relationSceneType=r.get("relation_scene_type"),
                    ownerType=str(
                        r.get("owner_type", r.get("ownerType", "enterprise"))
                    ),
                    userCode=r.get("user_code") or r.get("userCode"),
                )
            else:
                continue
            result.append(rel.model_dump(by_alias=True))
        if keyword:
            kw = keyword.strip().lower()
            result = [
                r
                for r in result
                if kw in (r.get("relationName", "") or "").lower()
                or kw in (r.get("relationCode", "") or "").lower()
                or kw in (r.get("relationDesc", "") or "").lower()
            ]
        return result

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the loaded ontology."""
        for r in self.get_relations(loader, base_id):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def get_relations_by_object(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relation details where *object_code* is source or target.

        Supports owner_type/user_code filtering on the relations.

        Args:
            loader: An OntologyQueryable with _relations and _classes populated.
            base_id: Base / project identifier.
            object_code: Object to find relations for (bidirectional — source or target).
            owner_type: Filter relations by owner_type.
            user_code: Filter by user_code when owner_type is personal.

        Returns:
            List of relation dicts (full detail, alias-mapped).
        """
        all_relations = self.get_relations(loader, base_id)
        result: list[dict[str, Any]] = []
        for r in all_relations:
            src: str = r.get("sourceObjectCode", "")
            tgt: str = r.get("targetObjectCode", "")
            if src != object_code and tgt != object_code:
                continue
            rel_owner: str = r.get("ownerType", "enterprise")
            if owner_type and rel_owner != owner_type:
                continue
            if owner_type == "personal" and user_code:
                rel_user: str | None = r.get("userCode")
                if rel_user != user_code:
                    continue
            result.append(r)
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

    # ── Action CRUD (stub — datacloud-data SDK does not yet support) ────────

    def get_actions(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for an object from the loaded ontology with optional filtering."""
        cls = loader._classes.get(object_code)
        if cls is None:
            return []
        result: list[dict[str, Any]] = [
            Action(
                actionCode=a.action_code,
                actionName=a.action_name,
                actionType=a.action_type,
                belongObjectCode=a.belong_class,
                actionDesc=getattr(a, "description", None),
                requestUrl=getattr(a, "request_url", None),
                requestMethod=getattr(a, "request_method", None),
                ownerType=getattr(a, "owner_type", "enterprise"),
                userCode=getattr(a, "user_code", None),
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
            ).model_dump(by_alias=True)
            for a in getattr(cls, "actions", [])
        ]
        # keyword filter
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
        self, loader: Any, base_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Get single action detail by code from the loaded ontology."""
        for a in self.get_actions(loader, base_id, object_code):
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
        loader: Any,
        base_id: str,
        *,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all datasources from the loaded ontology.

        Scans all classes in the loader, collects unique dbId values from
        field definitions, and wraps them as Datasource dicts.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.

        Returns:
            List of Datasource dicts (alias-mapped).
        """
        _ = base_id
        used_db_ids: set[str] = set()
        for cls in loader._classes.values():
            db_id: str = getattr(cls, "datasource_alias", "") or ""
            if db_id:
                used_db_ids.add(db_id)

        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(
                DbConnection(
                    dbId=db_id,
                    dbCode=db_id,
                    dbType="",
                    dbParams={},
                )
            )
        if not dbs:
            return []
        return [Datasource(db=dbs).model_dump(by_alias=True)]

    def get_datasource_detail(
        self, loader: Any, base_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.
            db_id: Database identifier to look up.

        Returns:
            Datasource dict if found, otherwise None.
        """
        _ = base_id
        used_db_ids: set[str] = set()
        for cls in loader._classes.values():
            for f in cls.fields:
                field_db_id: str = getattr(f, "db", "") or ""
                if field_db_id:
                    used_db_ids.add(field_db_id)

        if db_id not in used_db_ids:
            return None

        db_conn = DbConnection(
            dbId=db_id,
            dbCode=db_id,
            dbType="",
            dbParams={},
        )
        return Datasource(db=[db_conn]).model_dump(by_alias=True)

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
        for view in views:
            code = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            name = view.get("view_name", "")
            if code and name:
                entities.append(("view", code, name))
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
        """
        _ = entity_desc, fields
        try:
            from datacloud_knowledge.adapters import (  # noqa: PLC0415
                backfill_embeddings,
                create_writer,
            )

            term_type_code = self._TERM_TYPE_MAP.get(entity_type, entity_type)
            domains = list(domain_codes) if domain_codes else []

            with create_writer() as writer:
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
            if term_id:
                import threading

                def _backfill() -> None:
                    try:
                        backfill_embeddings(term_ids=[term_id], batch_size=50)
                    except Exception:
                        logger.exception(
                            "_sync_entity_terms: embedding backfill failed "
                            "type=%s code=%s term_id=%s",
                            entity_type,
                            entity_code,
                            term_id,
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

        Reads the existing term by ``term_code = entity_code``, merges
        ``scene_id`` into its domain_ids set, and writes the merged list
        back via ``update_term``.  Existing scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            with create_writer() as writer:
                for entity_code in entity_codes:
                    try:
                        terms = reader.get_terms_batch_raw(term_codes=[entity_code])  # type: ignore[attr-defined]
                        if not terms:
                            logger.warning(
                                "_sync_entity_domains: term not found for code=%s",
                                entity_code,
                            )
                            continue
                        term_id = str(terms[0].get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = terms[0].get("domain_ids") or []
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

        Reads the existing term by ``term_code = entity_code``, removes
        ``scene_id`` from its domain_ids set, and writes the result back
        via ``update_term``.  Other scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            with create_writer() as writer:
                for entity_code in entity_codes:
                    try:
                        terms = reader.get_terms_batch_raw(term_codes=[entity_code])  # type: ignore[attr-defined]
                        if not terms:
                            logger.warning(
                                "_remove_entity_domains: term not found for code=%s",
                                entity_code,
                            )
                            continue
                        term_id = str(terms[0].get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = terms[0].get("domain_ids") or []
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
