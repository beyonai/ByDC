"""OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.adapters.json_entity_store import JsonEntityStore
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
from datacloud_platform.platform_file_storage import atomic_write_json

logger = logging.getLogger(__name__)


class OntologyBackendMixin(DataCloudDataBackendBase):
    """OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

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

    def save_parsed_content(
        self, base_path: Path, parsed: ParsedOwlContent
    ) -> dict[str, int]:
        """Persist parsed OWL content as ``objects_registry.json`` + shard files.

        Writes a unified JSON registry for fast :meth:`load_ontology` loads and
        individual shard files for detail queries.  Rebuilds indexes for all
        three entity types on completion.

        Args:
            base_path: Root directory for the ontology base.
            parsed: Structured parse result from :meth:`parse_owl`.

        Returns:
            Counts dict with ``objects``, ``views``, ``relations`` keys.
        """
        entity_store = JsonEntityStore(base_path)

        counts: dict[str, int] = {"objects": 0, "views": 0, "relations": 0}

        # Write unified JSON registry (fast-load path)
        registry: dict[str, list[dict[str, Any]]] = {
            "objects": parsed.objects,
            "views": parsed.views,
            "relations": parsed.relations,
        }
        base_path.mkdir(parents=True, exist_ok=True)
        atomic_write_json(base_path / "objects_registry.json", registry)

        # Write per-object shard files
        for obj in parsed.objects:
            obj_code: str = obj.get("object_code", "") or ""
            if obj_code:
                entity_store.save("objects", obj_code, obj)
                counts["objects"] += 1

        # Write per-view shard files
        for view in parsed.views:
            v_code: str = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            if v_code:
                entity_store.save("views", v_code, view)
                counts["views"] += 1

        # Write per-relation shard files
        for rel in parsed.relations:
            r_code: str = rel.get("relation_code", rel.get("relationCode", "")) or ""
            if r_code:
                entity_store.save("relations", r_code, rel)
                counts["relations"] += 1

        # Rebuild all indexes
        for et in ("objects", "views", "relations"):
            entity_store.save_index(et, entity_store.rebuild_index(et))

        logger.info(
            "save_parsed_content: %s objects=%d views=%d relations=%d",
            base_path,
            counts["objects"],
            counts["views"],
            counts["relations"],
        )
        return counts

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into a queryable runtime object.

        Prefers ``objects_registry.json`` (single file, < 1s) when available.
        On first access without a registry, parses OWL, persists the registry
        via ``parse_owl()`` + ``save_parsed_content()`` (same pipeline as
        ``import-owl``), then loads from the newly created registry.

        Args:
            base_path: Path to the OWL resource directory root.

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        # Fast path: unified JSON registry (< 1s)
        registry = base_path / "objects_registry.json"
        if registry.exists():
            content = _json.loads(registry.read_text(encoding="utf-8"))
            loader = OntologyLoader()
            loader.load_from_content(content)
            return loader  # type: ignore[no-any-return]

        # Fallback: OWL directory exists but no registry yet —
        # parse → persist (same pipeline as import-owl) → fast path
        if base_path.exists():
            logger.info(
                "objects_registry.json not found in %s, "
                "falling back to parse_owl + save_parsed_content",
                base_path,
            )
            parsed = self.parse_owl(base_path)
            self.save_parsed_content(base_path, parsed)
            return self.load_ontology(base_path)  # recurse → hits fast path above

        # No OWL directory, return empty loader
        return OntologyLoader()  # type: ignore[no-any-return]

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
        return TermLoader()

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
        self, loader: OntologyQueryable, base_id: str
    ) -> list[ObjectSummary]:
        """Get all object summaries under a base.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.

        Returns:
            List of ObjectSummary for every class in the loader.
        """
        _ = base_id
        return [self._to_summary(cls) for cls in loader._classes.values()]

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
        """Persist a new ontology object via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            obj: ObjectType dict or pydantic model.

        Returns:
            The saved object dict.

        Raises:
            ValueError: If object_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        code: str = obj_dict.get("object_code") or obj_dict.get("objectCode", "")
        if not code:
            raise ValueError("object_code is required for object creation")
        entity_store.save("objects", code, obj_dict)
        self._incremental_save(entity_store, "objects", code, obj_dict)
        logger.info("Created object: base_id=%s object_code=%s", base_id, code)
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
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        entity_store.save("objects", object_code, obj_dict)
        self._incremental_save(entity_store, "objects", object_code, obj_dict)
        logger.info("Updated object: base_id=%s object_code=%s", base_id, object_code)
        return obj_dict

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Delete an ontology object.

        Args:
            base_id: Base / project identifier.
            object_code: Target object code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("objects", object_code)
        self._incremental_delete(entity_store, "objects", object_code)
        logger.info("Deleted object: base_id=%s object_code=%s", base_id, object_code)

    # ── View CRUD ──────────────────────────────────────────────────────────

    def get_views(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all views from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _views populated.
            base_id: Base / project identifier.

        Returns:
            List of View dicts (alias-mapped).
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        result: list[dict[str, Any]] = []
        for vc, view_data in raw_views.items():
            normalized_codes = _normalize_object_codes(view_data.get("objects", []))
            view = View(
                viewCode=view_data.get("view_id", vc),
                viewName=view_data.get("view_name", ""),
                description=view_data.get("description"),
                objectCodes=normalized_codes,
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
            result.append(view.model_dump(by_alias=True))
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

    def create_view(self, base_id: str, view: Any) -> Any:
        """Persist a new view via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            view: View dict or pydantic model.

        Returns:
            The saved view dict.

        Raises:
            ValueError: If view_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
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
        self._incremental_save(entity_store, "views", code, view_dict)
        logger.info("Created view: base_id=%s view_code=%s", base_id, code)
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
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        view_dict: dict[str, Any] = (
            view if isinstance(view, dict) else view.model_dump(by_alias=True)
        )
        entity_store.save("views", view_code, view_dict)
        self._incremental_save(entity_store, "views", view_code, view_dict)
        logger.info("Updated view: base_id=%s view_code=%s", base_id, view_code)
        return view_dict

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Delete a view.

        Args:
            base_id: Base / project identifier.
            view_code: Target view code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("views", view_code)
        self._incremental_delete(entity_store, "views", view_code)
        logger.info("Deleted view: base_id=%s view_code=%s", base_id, view_code)

    # ── Relation CRUD (stub — datacloud-data SDK does not yet support) ──────

    def get_relations(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
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
                )
            else:
                continue
            result.append(rel.model_dump(by_alias=True))
        return result

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the loaded ontology."""
        for r in self.get_relations(loader, base_id):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, rel: Any) -> Any:
        """Persist a new relation via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            rel: Relation dict or pydantic model.

        Returns:
            The saved relation dict.

        Raises:
            ValueError: If relation_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        code: str = rel_dict.get("relation_code") or rel_dict.get("relationCode", "")
        if not code:
            raise ValueError("relation_code is required for relation creation")
        entity_store.save("relations", code, rel_dict)
        self._incremental_save(entity_store, "relations", code, rel_dict)
        logger.info("Created relation: base_id=%s relation_code=%s", base_id, code)
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
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        entity_store.save("relations", rel_code, rel_dict)
        self._incremental_save(entity_store, "relations", rel_code, rel_dict)
        logger.info("Updated relation: base_id=%s rel_code=%s", base_id, rel_code)
        return rel_dict

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Delete a relation.

        Args:
            base_id: Base / project identifier.
            rel_code: Target relation code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("relations", rel_code)
        self._incremental_delete(entity_store, "relations", rel_code)
        logger.info("Deleted relation: base_id=%s rel_code=%s", base_id, rel_code)

    # ── Action CRUD (stub — datacloud-data SDK does not yet support) ────────

    def get_actions(
        self, loader: Any, base_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Get all actions for an object from the loaded ontology."""
        cls = loader._classes.get(object_code)
        if cls is None:
            return []
        return [
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
            ).model_dump(by_alias=True)
            for a in getattr(cls, "actions", [])
        ]

    def get_action_detail(
        self, loader: Any, base_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Get single action detail by code from the loaded ontology."""
        for a in self.get_actions(loader, base_id, object_code):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(self, base_id: str, object_code: str, action: Any) -> Any:
        """Persist a new action under an object via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action: Action dict or pydantic model.

        Returns:
            The saved action dict.

        Raises:
            ValueError: If action_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        code: str = action_dict.get("action_code") or action_dict.get("actionCode", "")
        if not code:
            raise ValueError("action_code is required for action creation")
        # Ensure parent object_code is recorded
        action_dict["belongObjectCode"] = object_code
        entity_store.save("actions", code, action_dict)
        self._incremental_save(entity_store, "actions", code, action_dict)
        logger.info(
            "Created action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            code,
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
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        action_dict["belongObjectCode"] = object_code
        entity_store.save("actions", action_code, action_dict)
        self._incremental_save(entity_store, "actions", action_code, action_dict)
        logger.info(
            "Updated action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
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
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("actions", action_code)
        self._incremental_delete(entity_store, "actions", action_code)
        logger.info(
            "Deleted action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
        )

    # ── Datasource CRUD ────────────────────────────────────────────────────

    def get_datasources(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
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
        """Persist a new datasource via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            ds: Datasource dict or pydantic model.

        Returns:
            The saved datasource dict.

        Raises:
            ValueError: If db_id is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
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
        self._incremental_save(entity_store, "datasources", db_id, ds_dict)
        logger.info("Created datasource: base_id=%s db_id=%s", base_id, db_id)
        return ds_dict

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Delete a datasource.

        Args:
            base_id: Base / project identifier.
            db_id: Target database identifier.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("datasources", db_id)
        self._incremental_delete(entity_store, "datasources", db_id)
        logger.info("Deleted datasource: base_id=%s db_id=%s", base_id, db_id)
