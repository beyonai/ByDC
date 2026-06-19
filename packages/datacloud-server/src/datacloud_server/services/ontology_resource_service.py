"""OntologyResourceService — Object / View / Relation / Action / Datasource CRUD (24 methods).

Injects AdapterRouter only — no duplicated _get_adapter logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View
    from datacloud_server.services.adapter_router import AdapterRouter

logger = logging.getLogger(__name__)


class OntologyResourceService:
    """CRUD operations for Object, View, Relation, Action, Datasource."""

    def __init__(self, router: AdapterRouter) -> None:
        self._router = router

    # -- Object CRUD --

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
        return self._router.get(base_id).get_objects(base_id, scene_id)

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        return self._router.get(base_id).get_object_detail(base_id, scene_id, object_code)

    def create_object(
        self,
        base_id: str,
        scene_id: str,
        obj: ObjectType,
        search_scope_extra: dict[str, Any] | None = None,
    ) -> ObjectType:
        result = self._router.get(base_id).create_object(base_id, scene_id, obj)
        # 扩展：若传入 search_scope_extra，写入 term 表（供 search_ontology 向量搜索命中）
        if search_scope_extra:
            try:
                from datacloud_knowledge.ingestion.ontology_terms import build_terms  # noqa: PLC0415

                fields = [
                    {
                        "property_code": p.propertyCode if hasattr(p, "propertyCode") else str(p),
                        "property_name": p.propertyName if hasattr(p, "propertyName") else str(p),
                        "data_type": "STRING",
                    }
                    for p in (obj.properties or [])
                ]
                build_terms(
                    entity_code=obj.objectCode,
                    entity_name=obj.objectName or obj.objectCode,
                    fields=fields,
                    entity_desc=obj.objectDesc or "",
                    search_scope_extra=search_scope_extra,
                )
                logger.info(
                    "create_object: build_terms done for %s scope=%s",
                    obj.objectCode,
                    search_scope_extra,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "create_object: build_terms failed for %s", obj.objectCode, exc_info=True
                )
        return result

    def update_object(
        self, base_id: str, scene_id: str, object_code: str, obj: ObjectType
    ) -> ObjectType:
        return self._router.get(base_id).update_object(base_id, scene_id, object_code, obj)

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        self._router.get(base_id).delete_object(base_id, scene_id, object_code)

    # -- View CRUD --

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        return self._router.get(base_id).get_views(base_id, scene_id)

    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None:
        return self._router.get(base_id).get_view_detail(base_id, scene_id, view_code)

    def create_view(self, base_id: str, scene_id: str, view: View) -> View:
        return self._router.get(base_id).create_view(base_id, scene_id, view)

    def update_view(self, base_id: str, scene_id: str, view_code: str, view: View) -> View:
        return self._router.get(base_id).update_view(base_id, scene_id, view_code, view)

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        self._router.get(base_id).delete_view(base_id, scene_id, view_code)

    # -- Relation CRUD --

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        return self._router.get(base_id).get_relations(base_id, scene_id)

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        return self._router.get(base_id).get_relation_detail(base_id, scene_id, rel_code)

    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation:
        return self._router.get(base_id).create_relation(base_id, scene_id, rel)

    def update_relation(
        self, base_id: str, scene_id: str, rel_code: str, rel: Relation
    ) -> Relation:
        return self._router.get(base_id).update_relation(base_id, scene_id, rel_code, rel)

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        self._router.get(base_id).delete_relation(base_id, scene_id, rel_code)

    # -- Datasource CRUD --

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]:
        return self._router.get(base_id).get_datasources(base_id, scene_id)

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        return self._router.get(base_id).get_datasource_detail(base_id, scene_id, db_id)

    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource:
        return self._router.get(base_id).create_datasource(base_id, scene_id, ds)

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        self._router.get(base_id).delete_datasource(base_id, scene_id, db_id)

    # -- Action CRUD --

    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]:
        return self._router.get(base_id).get_actions(base_id, scene_id, object_code)

    def get_action_detail(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
    ) -> dict | None:
        return self._router.get(base_id).get_action_detail(
            base_id,
            scene_id,
            object_code,
            action_code,
        )

    def create_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action: Action,
    ) -> Action:
        return self._router.get(base_id).create_action(
            base_id,
            scene_id,
            object_code,
            action,
        )

    def update_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        action: Action,
    ) -> Action:
        return self._router.get(base_id).update_action(
            base_id,
            scene_id,
            object_code,
            action_code,
            action,
        )

    def delete_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
    ) -> None:
        return self._router.get(base_id).delete_action(
            base_id,
            scene_id,
            object_code,
            action_code,
        )
