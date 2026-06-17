"""CloneScene — clone all objects/views/relations from source scene to target scene.

Orchestration use case verifying OntologyResourceService CRUD composition.
Failure compensation rollback stays inside the use case, not polluting atomic Services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from datacloud_server.models.object_type import ObjectType
from datacloud_server.models.relation import Relation
from datacloud_server.models.view import View

if TYPE_CHECKING:
    from datacloud_server.services.ontology_resource_service import OntologyResourceService


@dataclass
class CloneResult:
    """Result of a CloneScene operation."""

    objects: int = 0
    views: int = 0
    relations: int = 0


@dataclass
class CloneScene:
    """Clone scene: objects + views + relations -> target scene, with rollback on failure."""

    _resource: OntologyResourceService

    def __call__(self, base_id: str, source: str, target: str) -> CloneResult:
        """Clone all resources from source scene to target scene.

        Reads from source (no mutation), writes to target.
        Any write failure triggers rollback of already-created objects/views.
        """
        # 1. Read source scene resources
        src_objects = self._resource.get_objects(base_id, source)
        src_views = self._resource.get_views(base_id, source)
        src_relations = self._resource.get_relations(base_id, source)

        # 2. Convert dicts to domain models
        objects = [ObjectType(**o) for o in src_objects]
        views = [View(**v) for v in src_views]
        relations = [Relation(**r) for r in src_relations]

        created_object_codes: list[str] = []
        created_view_codes: list[str] = []

        try:
            # 3. Create in order: object -> view -> relation
            for obj in objects:
                created_obj = self._resource.create_object(base_id, target, obj)
                created_object_codes.append(created_obj.object_code)

            for view in views:
                created_view = self._resource.create_view(base_id, target, view)
                created_view_codes.append(created_view.view_code)

            for rel in relations:
                self._resource.create_relation(base_id, target, rel)

        except Exception:
            # 4. Rollback: delete created resources in reverse order
            for code in reversed(created_object_codes):
                self._resource.delete_object(base_id, target, code)
            for code in reversed(created_view_codes):
                self._resource.delete_view(base_id, target, code)
            raise

        return CloneResult(
            objects=len(created_object_codes),
            views=len(created_view_codes),
            relations=len(relations),
        )
