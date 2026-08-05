"""Frontend operation-form rendering for cascade delete."""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.executor.kb_cascade_delete.models import CascadeDeleteContext


def build_cascade_action_form(
    *,
    action_form: dict[str, Any],
    cascade_context: CascadeDeleteContext,
) -> dict[str, Any]:
    """Extend one existing operation action without exposing trusted identities."""
    cascade_children: list[list[dict[str, Any]]] = []
    for item in cascade_context.items:
        cascade_children.append(
            [
                {
                    "itemId": item.item_id,
                    "formType": "checkbox",
                    "fieldCode": "deleteSelected",
                    "fieldName": "同时删除",
                    "fieldType": "boolean",
                    "fieldValue": True,
                },
                {
                    "formType": "input",
                    "fieldCode": "objectName",
                    "fieldName": "对象类型",
                    "fieldType": "string",
                    "fieldValue": item.object_name or item.object_code,
                    "readonly": True,
                },
                {
                    "formType": "input",
                    "fieldCode": "filePath",
                    "fieldName": "文件路径",
                    "fieldType": "string",
                    "fieldValue": item.source_path,
                    "readonly": True,
                },
                {
                    "formType": "input",
                    "fieldCode": "uncheckedEffect",
                    "fieldName": "取消后的处理",
                    "fieldType": "string",
                    "fieldValue": "保留文件并解除关联",
                    "readonly": True,
                },
            ]
        )

    root_fields = [
        {
            "formType": "input",
            "fieldCode": "rootFile",
            "fieldName": "待删除文件",
            "fieldType": "string",
            "fieldValue": root.source_path,
            "readonly": True,
        }
        for root in cascade_context.roots
    ]
    cascade_field = {
        "formType": "array",
        "fieldCode": "cascadeFiles",
        "fieldName": "级联文件",
        "fieldType": "array<object>",
        "children": cascade_children,
    }
    return {
        **action_form,
        "formMode": "cascade_delete",
        "summary": {
            "rootCount": len(cascade_context.roots),
            "cascadeCount": len(cascade_context.items),
            "selectedDeleteCount": len(cascade_context.items),
            "detachCount": 0,
            "blockerCount": 0,
        },
        "description": "取消勾选的级联文件将保留，并解除与待删除上级的关联。",
        "rule": [[*root_fields, cascade_field]],
    }
