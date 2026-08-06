"""Helpers for invoking datacloud-data object actions from Platform services."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_platform.models.document import DocumentProcessingStatus
from datacloud_platform.mixins.document import build_processing_labels

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)
CONTENT_PREVIEW_CHARS = 800


async def invoke_object_write_action(
    *,
    platform: DatacloudPlatform,
    base_id: str,
    object_code: str,
    content: str,
    labels: dict[str, Any],
    file_description: str,
    source_path: str,
) -> dict[str, Any]:
    """Write one object instance document through the object's write action."""
    if not object_code.strip():
        raise ValueError("object_code is required")
    if not content.strip():
        raise ValueError("content is required")
    if not source_path.strip():
        raise ValueError("source_path is required")

    return await invoke_object_action(
        platform=platform,
        base_id=base_id,
        object_code=object_code,
        action_code=f"write_{object_code}",
        arguments={
            "source_path": source_path,
            "content": content,
            "labels": labels,
            "file_description": file_description,
        },
    )


async def invoke_object_action(
    *,
    platform: DatacloudPlatform,
    base_id: str,
    object_code: str,
    action_code: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Invoke an object action using the same loader pipeline as kb.invokeAction."""
    arguments = prepare_action_arguments(action_code=action_code, arguments=arguments)
    loader = platform._load_ontology_cached(base_id)  # noqa: SLF001
    if isinstance(loader, OntologyLoader):
        loader.configure(platform=platform)
    platform.inject_virtual_actions(base_id, loader)

    get_object = getattr(loader, "get_object", None)
    transport = "loader_object" if callable(get_object) else "platform_execute_action"
    logger.info(
        "object_action invoke start: base_id=%s object_code=%s action_code=%s "
        "transport=%s arguments=%s",
        base_id,
        object_code,
        action_code,
        transport,
        _json_for_log(_summarize_arguments(arguments)),
    )
    try:
        if callable(get_object):
            target_object = get_object(object_code)
            action_result = await target_object.invoke_action(action_code, arguments)
        else:
            action_result = await platform.execute_action(
                base_id,
                loader,
                object_code,
                action_code,
                arguments,
            )
        result = unwrap_action_result(action_result)
    except Exception:
        logger.exception(
            "object_action invoke failed: base_id=%s object_code=%s action_code=%s "
            "transport=%s arguments=%s",
            base_id,
            object_code,
            action_code,
            transport,
            _json_for_log(_summarize_arguments(arguments)),
        )
        raise

    logger.info(
        "object_action invoke succeeded: base_id=%s object_code=%s action_code=%s "
        "transport=%s result=%s",
        base_id,
        object_code,
        action_code,
        transport,
        _json_for_log(_summarize_result(result)),
    )
    return result


def prepare_action_arguments(
    *, action_code: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Add DataCloud processing labels to document write actions."""
    if not action_code.startswith("write_"):
        return arguments
    prepared = dict(arguments)
    raw_labels = prepared.get("labels")
    if raw_labels is not None and not isinstance(raw_labels, Mapping):
        raise ValueError("arguments.labels must be an object")
    prepared["labels"] = build_processing_labels(
        initial_status=DocumentProcessingStatus.PENDING_DISCOVERY,
        labels=raw_labels,
    )
    return prepared


def unwrap_action_result(action_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize action result envelopes into a data dict."""
    content = action_result.get("content") or []
    if content:
        text = content[0].get("text", "") if isinstance(content[0], dict) else ""
        if not text:
            return action_result
        try:
            inner = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return action_result
        inner_code = int(inner.get("code") or 0)
        if inner_code not in (0, 200):
            raise RuntimeError(inner.get("message") or f"action failed: {inner_code}")
        return _normalize_data(inner.get("data") or {})

    data = action_result.get("data")
    if isinstance(data, dict):
        return _normalize_data(data)
    return action_result


def _normalize_data(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "records": data.get("records") or [],
        "total": data.get("total") or data.get("meta", {}).get("total") or 0,
        "meta": data.get("meta") or {},
    }


def _summarize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if key == "content":
            text = str(value or "")
            summary["content_length"] = len(text)
            summary["content_head_preview"] = text[:CONTENT_PREVIEW_CHARS]
            summary["content_tail_preview"] = text[-CONTENT_PREVIEW_CHARS:]
        else:
            summary[key] = value
    return summary


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    records = result.get("records")
    meta = result.get("meta")
    return {
        "record_count": len(records) if isinstance(records, list) else 0,
        "total": result.get("total") or 0,
        "meta_keys": sorted(meta) if isinstance(meta, dict) else [],
    }


def _json_for_log(data: dict[str, Any]) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return json.dumps({"repr": repr(data)}, ensure_ascii=False, sort_keys=True)
