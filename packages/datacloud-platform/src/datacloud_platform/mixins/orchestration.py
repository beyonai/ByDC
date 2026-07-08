"""OrchestrationMixin — cross-Backend workflows such as OWL import."""

from __future__ import annotations

import io
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class OrchestrationMixin:
    """Mixin for cross-backend orchestration workflows: OWL import, etc."""

    def import_owl(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        zip_bytes: bytes,
    ) -> dict[str, Any]:
        """Import an OWL zip: unzip → parse → write objects/views/relations → sync terms.

        Returns a summary dict: ``{"objects": N, "views": N, "relations": N, "actions": N, "dbsources": N}``.
        """
        onto = self._ontology_for(base_id)
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]

        # 0. Resolve scene — delegate to SceneServiceMixin for shared default-scene logic
        if not scene_id:
            scene_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
            logger.info("Auto-resolved default scene: scene_id=%s", scene_id)

        # 1. Unzip
        extract_dir = Path(tempfile.mkdtemp(prefix="owl_import_"))
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            zf.extractall(extract_dir)

        # 2. Parse
        parsed = onto.parse_owl(extract_dir)

        # 3. Batch import ontology content into backend
        counts: dict[str, int] = onto.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
            base_id=base_id,
        )

        # 3.5 Add imported objects/views to the scene's member list
        object_codes = [
            obj.get("object_code", "")
            for obj in parsed.objects
            if obj.get("object_code")
        ]
        view_codes = [
            v.get("view_id", v.get("view_code", ""))
            for v in parsed.views
            if v.get("view_id") or v.get("view_code")
        ]
        if object_codes or view_codes:
            try:
                onto.add_scene_members(base_id, scene_id, object_codes, view_codes)
                logger.info(
                    "Added %d objects + %d views to scene %s",
                    len(object_codes),
                    len(view_codes),
                    scene_id,
                )
            except Exception as exc:
                logger.warning("Failed to add scene members: %s", exc)

        # 5. Cleanup
        shutil.rmtree(extract_dir, ignore_errors=True)

        return counts
