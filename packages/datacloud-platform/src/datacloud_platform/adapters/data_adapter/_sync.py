"""Term sync — sync_terms, remove_terms."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SyncMixin:
    """Term sync — sync_terms, remove_terms."""

    # ── Sync ────────────────────────────────────────────────────────────

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Sync object term metadata into the knowledge DB."""
        from datacloud_knowledge.ingestion.term_sync import (  # noqa: PLC0415
            sync_object_terms,
        )

        sync_object_terms(
            entity_code=entity_code,
            entity_name=entity_name,
            entity_source=entity_source,
            fields=fields,
            backfill_vectors=backfill_vectors,
        )

    def remove_terms(self, entity_code: str) -> None:
        """Remove all terms associated with an object."""
        from datacloud_knowledge.ingestion.term_sync import (  # noqa: PLC0415
            remove_object_terms,
        )

        remove_object_terms(entity_code)
