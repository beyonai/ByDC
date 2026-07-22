"""Helpers for invoking datacloud-data object actions from Platform services."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.ontology.loader import OntologyLoader

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


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
    loader = platform._load_ontology_cached(base_id)  # noqa: SLF001
    if isinstance(loader, OntologyLoader):
        loader.configure(platform=platform)
    platform.inject_virtual_actions(base_id, loader)

    get_object = getattr(loader, "get_object", None)
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
    return unwrap_action_result(action_result)


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
