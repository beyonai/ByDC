"""Built-in tool hook: semantic-aware parameter enhancement."""

from __future__ import annotations

from typing import Any

PLUGIN_ID = "builtin.semantic_param_enhancer"
PRIORITY = 200
ENABLED = True


def _first_term_by_semantic(term_context: list[dict[str, Any]], semantic_type: str) -> dict[str, Any] | None:
    for item in term_context:
        if not isinstance(item, dict):
            continue
        if str(item.get("semantic_type") or "").strip().lower() == semantic_type:
            return item
    return None


def _append_snippet(text: str) -> list[dict[str, Any]]:
    return [{"source": "builtin.semantic_param_enhancer", "text": text}]


def before_call_back(ctx: dict[str, Any]) -> dict[str, Any] | None:
    term_context = list(ctx.get("term_context") or [])
    if not term_context:
        return None

    patched: dict[str, Any] = {}
    notes: list[str] = []

    view_term = _first_term_by_semantic(term_context, "view")
    if view_term is not None:
        view_name = str(view_term.get("normalized_term") or view_term.get("mention") or "").strip()
        if view_name and not str((ctx.get("tool_params") or {}).get("view_name") or "").strip():
            patched["view_name"] = view_name
            notes.append(f"补全view_name={view_name}")

    object_term = _first_term_by_semantic(term_context, "object")
    if object_term is not None:
        object_name = str(object_term.get("normalized_term") or object_term.get("mention") or "").strip()
        if object_name and not str((ctx.get("tool_params") or {}).get("object_name") or "").strip():
            patched["object_name"] = object_name
            notes.append(f"补全object_name={object_name}")

    action_term = _first_term_by_semantic(term_context, "action")
    if action_term is not None:
        action_name = str(action_term.get("normalized_term") or action_term.get("mention") or "").strip()
        if action_name and not str((ctx.get("tool_params") or {}).get("action_name") or "").strip():
            patched["action_name"] = action_name
            notes.append(f"补全action_name={action_name}")

    relation_term = _first_term_by_semantic(term_context, "relation")
    if relation_term is not None:
        relation_hint = str(
            relation_term.get("normalized_term") or relation_term.get("mention") or ""
        ).strip()
        if relation_hint and not str((ctx.get("tool_params") or {}).get("relation_hint") or "").strip():
            patched["relation_hint"] = relation_hint
            notes.append(f"补全relation_hint={relation_hint}")

    if not patched:
        return None

    return {
        "action": "patch",
        "patch": {
            "tool_params": patched,
            "knowledge_snippets_append": _append_snippet("；".join(notes)),
        },
        "audit": {
            "plugin_id": PLUGIN_ID,
            "message": "semantic_type 参数增强",
            "risk_level": "low",
        },
    }
