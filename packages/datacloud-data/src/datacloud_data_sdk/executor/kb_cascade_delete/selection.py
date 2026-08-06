"""Validate cascade checkboxes and produce a signed internal execution payload."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from datacloud_data_sdk.executor.kb_cascade_delete.models import CascadeDeleteContext


class CascadeSelectionError(ValueError):
    """Raised when a resumed cascade form cannot be trusted."""


_PROCESS_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    value = os.environ.get("DATACLOUD_CASCADE_DELETE_SECRET")
    return value.encode() if value else _PROCESS_SECRET


def _normalize_checkbox_value(value: Any) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise CascadeSelectionError("CASCADE_ITEM_TAMPERED: itemId 和 deleteSelected 必须有效")


def extract_cascade_selections(rule: list[Any]) -> dict[str, bool]:
    """Read only itemId/deleteSelected pairs from the complete returned form."""
    selections: dict[str, bool] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, dict):
            return
        if value.get("fieldCode") == "deleteSelected":
            item_id = str(value.get("itemId") or "")
            if not item_id:
                raise CascadeSelectionError(
                    "CASCADE_ITEM_TAMPERED: itemId 和 deleteSelected 必须有效"
                )
            field_value = _normalize_checkbox_value(value.get("fieldValue"))
            if item_id in selections:
                raise CascadeSelectionError(f"CASCADE_ITEM_TAMPERED: itemId 重复: {item_id}")
            selections[item_id] = field_value
        for child in value.values():
            if isinstance(child, (list, dict)):
                visit(child)

    visit(rule)
    return selections


def build_signed_cascade_execution(
    *,
    context: CascadeDeleteContext,
    selections: dict[str, bool],
    form_id: str,
    tool_call_id: str,
) -> dict[str, Any]:
    expires_at = datetime.fromisoformat(context.expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise CascadeSelectionError("CASCADE_CONTEXT_EXPIRED")

    expected_ids = {item.item_id for item in context.items}
    if set(selections) != expected_ids:
        raise CascadeSelectionError("CASCADE_ITEM_TAMPERED: itemId 集合不一致")

    item_by_id = {item.item_id: item for item in context.items}
    resolved: dict[str, str] = {}
    for item in sorted(context.items, key=lambda current: current.depth):
        ancestor_action = (
            resolved.get(item.parent_item_id) if item.parent_item_id is not None else None
        )
        if ancestor_action in {"DETACH", "KEEP_WITH_ANCESTOR"}:
            resolved[item.item_id] = "KEEP_WITH_ANCESTOR"
        elif selections[item.item_id]:
            resolved[item.item_id] = "DELETE"
        else:
            resolved[item.item_id] = "DETACH"

    def serialize(item_id: str) -> dict[str, Any]:
        item = item_by_id[item_id]
        return {
            "itemId": item.item_id,
            "parentItemId": item.parent_item_id,
            "depth": item.depth,
            "objectCode": item.object_code,
            "sourcePath": item.source_path,
            "termId": item.term_id,
            "relationId": item.relation_id,
            "relationCode": item.relation_code,
            "ownerTermId": item.owner_term_id,
            "fileFingerprint": item.file_fingerprint,
            "joinKeys": [dict(key) for key in item.join_keys],
        }

    payload = {
        "formId": form_id,
        "toolCallId": tool_call_id,
        "expiresAt": context.expires_at,
        "graphFingerprint": context.graph_fingerprint,
        "ontologyRevision": context.ontology_revision,
        "roots": context.to_dict()["roots"],
        "deleteItems": [
            serialize(item.item_id) for item in context.items if resolved[item.item_id] == "DELETE"
        ],
        "detachItems": [
            serialize(item.item_id) for item in context.items if resolved[item.item_id] == "DETACH"
        ],
        "keptItems": [
            serialize(item.item_id)
            for item in context.items
            if resolved[item.item_id] == "KEEP_WITH_ANCESTOR"
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_secret(), encoded, hashlib.sha256).hexdigest()
    return {"payload": payload, "contextSignature": signature}


def verify_signed_cascade_execution(value: dict[str, Any]) -> dict[str, Any]:
    payload = value.get("payload")
    signature = str(value.get("contextSignature") or "")
    if not isinstance(payload, dict) or not signature:
        raise CascadeSelectionError("CASCADE_CONTEXT_INVALID")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    expected = hmac.new(_secret(), encoded, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise CascadeSelectionError("CASCADE_CONTEXT_INVALID")
    expires_at = datetime.fromisoformat(str(payload.get("expiresAt") or ""))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise CascadeSelectionError("CASCADE_CONTEXT_EXPIRED")
    return payload
