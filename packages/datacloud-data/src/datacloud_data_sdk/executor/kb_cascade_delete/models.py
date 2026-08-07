"""Serializable trusted context models for cascade delete."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class CascadeDeleteRoot:
    object_code: str
    source_path: str
    term_id: str
    file_fingerprint: str


@dataclass(frozen=True)
class CascadeDeleteItem:
    item_id: str
    parent_item_id: str | None
    depth: int
    object_code: str
    object_name: str
    source_path: str
    term_id: str
    relation_id: str
    relation_code: str
    owner_term_id: str
    file_fingerprint: str
    join_keys: tuple[dict[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CascadeDeleteContext:
    ontology_revision: str
    graph_fingerprint: str
    expires_at: str
    roots: tuple[CascadeDeleteRoot, ...]
    items: tuple[CascadeDeleteItem, ...]

    @classmethod
    def create(
        cls,
        *,
        roots: list[CascadeDeleteRoot],
        items: list[CascadeDeleteItem],
        ontology_revision: str = "",
        ttl_minutes: int = 15,
    ) -> CascadeDeleteContext:
        graph_data = {
            "roots": [asdict(root) for root in roots],
            "items": [asdict(item) for item in items],
        }
        graph_fingerprint = hashlib.sha256(
            json.dumps(
                graph_data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        expires_at = (datetime.now(UTC) + timedelta(minutes=ttl_minutes)).isoformat()
        return cls(
            ontology_revision=ontology_revision,
            graph_fingerprint=graph_fingerprint,
            expires_at=expires_at,
            roots=tuple(roots),
            items=tuple(items),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontologyRevision": self.ontology_revision,
            "graphFingerprint": self.graph_fingerprint,
            "expiresAt": self.expires_at,
            "roots": [
                {
                    "objectCode": root.object_code,
                    "sourcePath": root.source_path,
                    "termId": root.term_id,
                    "fileFingerprint": root.file_fingerprint,
                }
                for root in self.roots
            ],
            "items": [
                {
                    "itemId": item.item_id,
                    "parentItemId": item.parent_item_id,
                    "depth": item.depth,
                    "objectCode": item.object_code,
                    "objectName": item.object_name,
                    "sourcePath": item.source_path,
                    "termId": item.term_id,
                    "relationId": item.relation_id,
                    "relationCode": item.relation_code,
                    "ownerTermId": item.owner_term_id,
                    "fileFingerprint": item.file_fingerprint,
                    "joinKeys": [dict(key) for key in item.join_keys],
                }
                for item in self.items
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CascadeDeleteContext:
        return cls(
            ontology_revision=str(data.get("ontologyRevision") or ""),
            graph_fingerprint=str(data.get("graphFingerprint") or ""),
            expires_at=str(data.get("expiresAt") or ""),
            roots=tuple(
                CascadeDeleteRoot(
                    object_code=str(root.get("objectCode") or ""),
                    source_path=str(root.get("sourcePath") or ""),
                    term_id=str(root.get("termId") or ""),
                    file_fingerprint=str(root.get("fileFingerprint") or ""),
                )
                for root in data.get("roots") or []
                if isinstance(root, dict)
            ),
            items=tuple(
                CascadeDeleteItem(
                    item_id=str(item.get("itemId") or ""),
                    parent_item_id=(
                        str(item.get("parentItemId"))
                        if item.get("parentItemId") is not None
                        else None
                    ),
                    depth=int(item.get("depth") or 0),
                    object_code=str(item.get("objectCode") or ""),
                    object_name=str(item.get("objectName") or ""),
                    source_path=str(item.get("sourcePath") or ""),
                    term_id=str(item.get("termId") or ""),
                    relation_id=str(item.get("relationId") or ""),
                    relation_code=str(item.get("relationCode") or ""),
                    owner_term_id=str(item.get("ownerTermId") or ""),
                    file_fingerprint=str(item.get("fileFingerprint") or ""),
                    join_keys=tuple(
                        dict(key) for key in item.get("joinKeys") or [] if isinstance(key, dict)
                    ),
                )
                for item in data.get("items") or []
                if isinstance(item, dict)
            ),
        )
