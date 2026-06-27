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

        Returns a summary dict: ``{"objects": N, "views": N, "relations": N}``.
        """
        onto = self._ontology_for(base_id)
        # knowledge backend accessed via duck-typing (not all mixins provide it)
        know = self._knowledge_for(base_id)  # type: ignore[attr-defined]
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]

        # 1. Unzip
        extract_dir = Path(tempfile.mkdtemp(prefix="owl_import_"))
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            zf.extractall(extract_dir)

        # 2. Parse
        parsed = onto.parse_owl(extract_dir)

        # 3. Write to storage (save_parsed_content or individual create_object fallback)
        if hasattr(onto, "save_parsed_content"):
            counts: dict[str, int] = onto.save_parsed_content(base_path, parsed)
        else:
            # Fallback for remote / legacy adapters without save_parsed_content
            counts = {"objects": 0, "views": 0, "relations": 0}
            for obj_dict in parsed.objects:
                try:
                    onto.create_object(base_id, obj_dict)
                    counts["objects"] += 1
                except Exception as exc:
                    logger.warning("Failed to create object from OWL import: %s", exc)
            counts["views"] = len(parsed.views)
            counts["relations"] = len(parsed.relations)

        # 4. Sync terms for each object
        for obj_dict in parsed.objects:
            try:
                code: str = obj_dict.get("object_code", "")
                name: str = obj_dict.get("object_name", "")
                source: str = obj_dict.get("object_source", "")
                fields: list[dict[str, Any]] = obj_dict.get("properties", [])
                know.sync_terms(
                    code,
                    name,
                    source,
                    fields,
                    backfill_vectors=True,
                )
            except Exception as exc:
                logger.warning("Failed to sync terms for object: %s", exc)

        # 5. Cleanup
        shutil.rmtree(extract_dir, ignore_errors=True)

        return counts
