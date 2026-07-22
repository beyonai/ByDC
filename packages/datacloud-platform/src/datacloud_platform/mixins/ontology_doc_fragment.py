"""OntologyDocFragmentMixin — batch create / list / status-update for doc fragments.

Business logic:
  - batch_create_fragments: look up term details (term_name + origin_file from
    ext_attrs) for each (instance_id, origin_instance_id), then bulk-insert rows.
  - list_fragments_by_instance_ids: paginated query by instance_id list.
  - update_fragment_status_by_ids: bulk status update by primary-key id list.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasTermBackend

logger = logging.getLogger(__name__)


class OntologyDocFragmentMixin:
    """Mixin for ontology_doc_fragment CRUD operations."""

    # ── public API ─────────────────────────────────────────────────────────────

    def batch_create_fragments(
        self: _HasTermBackend,
        base_id: str,
        *,
        items: list[dict[str, Any]],
        created_by: str,
    ) -> list[dict[str, Any]]:
        """Batch-create doc fragment rows after enriching from term table.

        Each item must have:
          - instance_id (str): term_id for the instance term.
          - origin_instance_id (str | None): term_id for the origin-file term.
          - content (str): fragment text.

        Enrichment steps:
          1. Collect all unique term_ids (instance_id + origin_instance_id).
          2. Batch-fetch term details via TermBackend.get_term_detail.
          3. For each item resolve instance_name (term_name of instance_id) and
             origin_file dict (kb_resource_id / kb_id / file_path from
             ext_attrs of origin_instance_id).
          4. Bulk-insert via OntologyDocFragmentAdapter.

        Args:
            base_id: Base/project identifier used for term resolution.
            items: List of {instance_id, origin_instance_id?, content} dicts.
            created_by: Operator identifier written to created_by column.

        Returns:
            List of inserted fragment dicts (all columns) in the same order as items.
        """
        if not items:
            return []

        # ── 1. collect unique term_ids ─────────────────────────────────────
        term_ids: set[str] = set()
        for item in items:
            iid = item.get("instance_id") or ""
            if iid:
                term_ids.add(iid)
            oid = item.get("origin_instance_id") or ""
            if oid:
                term_ids.add(oid)

        # ── 2. batch-fetch term details (one call per unique id) ───────────
        term_cache: dict[str, dict[str, Any]] = {}
        for tid in term_ids:
            try:
                detail = self._term_for(base_id).get_term_detail(
                    library_id=base_id, term_id=tid
                )
                if detail:
                    if hasattr(detail, "__dict__") and not isinstance(detail, dict):
                        detail = vars(detail)
                    term_cache[tid] = detail  # type: ignore[assignment]
            except Exception:
                logger.warning(
                    "batch_create_fragments: failed to fetch term_id=%s", tid, exc_info=True
                )

        # ── 2a. validate all instance_ids exist ────────────────────────────
        instance_ids_in_items = {
            item.get("instance_id") or ""
            for item in items
            if item.get("instance_id")
        }
        missing = sorted(instance_ids_in_items - term_cache.keys())
        if missing:
            raise ValueError(
                f"以下 instance_id 在 term 表中不存在: {', '.join(missing)}"
            )

        # ── 3. build insert records ────────────────────────────────────────
        records: list[dict[str, Any]] = []
        for item in items:
            instance_id: str = item.get("instance_id") or ""
            origin_instance_id: str | None = item.get("origin_instance_id") or None
            content: str = item.get("content") or ""

            instance_name = _extract_term_name(term_cache.get(instance_id))

            origin_file: dict[str, Any] = {}
            if origin_instance_id:
                origin_file = _extract_origin_file(term_cache.get(origin_instance_id))

            records.append(
                {
                    "instance_id": instance_id,
                    "instance_name": instance_name,
                    "content": content,
                    "status": 0,
                    "origin_instance_id": origin_instance_id,
                    "origin_file": origin_file,
                    "created_by": created_by,
                }
            )

        # ── 4. bulk insert ─────────────────────────────────────────────────
        from datacloud_platform.adapters.data_adapter._ontology_doc_fragment import (  # noqa: PLC0415
            OntologyDocFragmentAdapter,
        )

        adapter = OntologyDocFragmentAdapter()
        return adapter.batch_create(records)

    def list_fragments_by_instance_ids(
        self,
        _base_id: str,  # noqa: ARG002
        *,
        instance_ids: list[str],
        page_index: int = 1,
        page_size: int = 20,
        status: int | None = None,
    ) -> dict[str, Any]:
        """Paginated query of fragments by instance_id list.

        Args:
            _base_id: Unused (kept for consistent call signature).
            instance_ids: List of instance_id values to filter by.
            page_index: 1-based page number.
            page_size: Records per page.
            status: Optional status filter — 0=未融合, 1=已融合. None means no filter.

        Returns:
            {"total": int, "data": [fragment_dict, ...]}
        """
        from datacloud_platform.adapters.data_adapter._ontology_doc_fragment import (  # noqa: PLC0415
            OntologyDocFragmentAdapter,
        )

        adapter = OntologyDocFragmentAdapter()
        return adapter.list_by_instance_ids(
            instance_ids, page_index=page_index, page_size=page_size, status=status
        )

    def update_fragment_status_by_ids(
        self,
        _base_id: str,  # noqa: ARG002
        *,
        ids: list[int],
        status: int,
        updated_by: str,
    ) -> int:
        """Bulk-update fragment status by primary-key id list.

        Args:
            _base_id: Unused (kept for consistent call signature).
            ids: List of primary-key ids to update.
            status: New status (0=未融合, 1=已融合).
            updated_by: Operator identifier.

        Returns:
            Number of rows actually updated.
        """
        from datacloud_platform.adapters.data_adapter._ontology_doc_fragment import (  # noqa: PLC0415
            OntologyDocFragmentAdapter,
        )

        adapter = OntologyDocFragmentAdapter()
        return adapter.update_status_by_ids(ids, status=status, updated_by=updated_by)


# ═══════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_term_name(detail: Any) -> str:
    """Extract term_name from a term detail dict or dataclass."""
    if not detail:
        return ""
    if isinstance(detail, dict):
        return str(detail.get("term_name") or detail.get("termName") or "")
    return str(getattr(detail, "term_name", "") or "")


def _extract_origin_file(detail: Any) -> dict[str, Any]:
    """Extract origin_file fields from term ext_attrs.

    Looks for kb_resource_id, kb_id, file_path inside:
      - detail["ext_attrs"]  (snake_case)
      - detail["extAttrs"]   (camelCase)
    """
    if not detail:
        return {}

    if isinstance(detail, dict):
        ext_attrs = detail.get("ext_attrs") or detail.get("extAttrs") or {}
    else:
        ext_attrs = getattr(detail, "ext_attrs", None) or {}

    if not isinstance(ext_attrs, dict):
        return {}

    result: dict[str, Any] = {}
    for key in ("kb_resource_id", "kb_id", "file_path"):
        val = ext_attrs.get(key)
        if val is not None:
            result[key] = val
    return result
