"""Discover and materialize workspace templates from a configured directory."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_WORKSPACE_CODE_PATTERN = re.compile(r"w[a-z0-9]{8,10}")
_USER_CODE_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class MaterializedWorkspaceTemplate:
    """Codes produced while materializing the template."""

    workspace_code: str
    object_codes: list[str]
    action_codes: list[str]


def default_workspace_templates_root() -> Path:
    """Return the first ontology template root found from known service launch dirs."""
    candidates = (
        Path("template") / "ontology",
        Path("byclaw-data") / "template" / "ontology",
        Path("ByClaw") / "byclaw-data" / "template" / "ontology",
    )
    return next(
        (candidate for candidate in candidates if candidate.is_dir()), candidates[0]
    )


def resolve_workspace_templates_directory(
    templates_root: Path, relative_directory: str
) -> Path:
    """Resolve a caller-provided directory below the configured template root."""
    relative = Path(relative_directory.strip() or ".")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("template_directory 必须是 template/ontology 下的相对路径")
    resolved_root = templates_root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("template_directory 必须是 template/ontology 下的相对路径")
    return resolved


def discover_workspace_templates(templates_root: Path) -> list[Path]:
    """Return direct child directories that contain a workspace manifest."""
    if not templates_root.is_dir():
        raise FileNotFoundError(f"工作区模板目录不存在: {templates_root}")
    return sorted(
        (
            child
            for child in templates_root.iterdir()
            if child.is_dir() and (child / "workspace.json").is_file()
        ),
        key=lambda path: path.name,
    )


def select_workspace_templates(
    templates_root: Path, template_directory: str
) -> list[Path]:
    """Select one named template, or all direct child templates for an empty name."""
    if not template_directory.strip():
        return discover_workspace_templates(templates_root)

    selected = resolve_workspace_templates_directory(templates_root, template_directory)
    if not selected.is_dir() or not (selected / "workspace.json").is_file():
        raise FileNotFoundError(f"工作区模板不存在: {selected}")
    return [selected]


def materialize_workspace_template(
    *,
    template_root: Path,
    destination_root: Path,
    workspace_name: str,
    user_code: str,
    is_personal: bool,
) -> MaterializedWorkspaceTemplate:
    """Copy and rewrite one template into a new workspace directory."""
    workspace_file = template_root / "workspace.json"
    if not workspace_file.is_file():
        raise FileNotFoundError(f"微信文章运营模板不存在: {template_root}")

    normalized_user_code = _normalize_user_code(user_code)
    template_state = _load_json_object(workspace_file)
    template_workspace_code = str(template_state.get("workspace_code", ""))
    if not _WORKSPACE_CODE_PATTERN.fullmatch(template_workspace_code):
        raise ValueError(f"模板缺少合法的 workspace_code: {template_root}")
    target_workspace_code = (
        _personal_workspace_code(normalized_user_code)
        if is_personal
        else template_workspace_code
    )
    template_object_codes = sorted(template_state.get("objects", {}))
    template_action_codes = _list_action_codes(template_root, template_object_codes)
    object_mapping = {
        code: code.replace(template_workspace_code, target_workspace_code, 1)
        for code in template_object_codes
    }
    action_mapping = {
        code: f"{target_workspace_code}_{code}" if is_personal else code
        for code in template_action_codes
    }
    materialized = MaterializedWorkspaceTemplate(
        workspace_code=target_workspace_code,
        object_codes=list(object_mapping.values()),
        action_codes=list(action_mapping.values()),
    )
    if destination_root.exists() and any(destination_root.iterdir()):
        existing_workspace_file = destination_root / "workspace.json"
        if existing_workspace_file.is_file():
            existing = _load_json_object(existing_workspace_file)
            if (
                existing.get("template_source") == template_root.name
                and existing.get("workspace_name") == workspace_name
                and existing.get("workspace_code") == target_workspace_code
                and existing.get("is_personal") is is_personal
            ):
                return materialized
        raise FileExistsError(f"工作区 {workspace_name!r} 已存在，不能覆盖")

    replacements = _build_replacements(object_mapping, action_mapping)

    destination_root.mkdir(parents=True, exist_ok=True)
    try:
        _copy_rewritten_template(template_root, destination_root, replacements)
        destination_workspace_file = destination_root / "workspace.json"
        state = _load_json_object(destination_workspace_file)
        state["workspace_name"] = workspace_name
        state["workspace_code"] = target_workspace_code
        state["template_source"] = template_root.name
        state["is_personal"] = is_personal
        state["objects"] = {
            object_mapping[code]: {
                **dict(summary),
                "status": "draft",
            }
            for code, summary in template_state.get("objects", {}).items()
        }
        state["views"] = {}
        destination_workspace_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(destination_root, ignore_errors=True)
        raise

    return materialized


def _normalize_user_code(user_code: str) -> str:
    normalized = user_code.strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("X-User-Code 不能为空")
    if not _USER_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("X-User-Code 只能包含字母、数字、下划线和连字符")
    return normalized


def _personal_workspace_code(user_code: str) -> str:
    candidate = user_code if user_code.startswith("w") else f"w{user_code}"
    if not _WORKSPACE_CODE_PATTERN.fullmatch(candidate):
        raise ValueError(
            f"个人用户编码加 w 前缀后必须匹配 w[a-z0-9]{{8,10}}，当前值为 {candidate!r}"
        )
    return candidate


def _load_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"模板 JSON 必须是对象: {path}")
    return loaded


def _list_action_codes(template_root: Path, object_codes: list[str]) -> list[str]:
    codes: set[str] = set()
    for object_code in object_codes:
        actions_root = template_root / "objects" / object_code / "actions"
        if actions_root.is_dir():
            codes.update(path.stem for path in actions_root.glob("*.json"))
    return sorted(codes)


def _build_replacements(
    object_mapping: dict[str, str], action_mapping: dict[str, str]
) -> list[tuple[str, str]]:
    replacements = {**object_mapping, **action_mapping}
    for source, target in object_mapping.items():
        replacements[_snake_to_pascal(source)] = _snake_to_pascal(target)
    return sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)


def _snake_to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))


def _replace(value: str, replacements: list[tuple[str, str]]) -> str:
    for source, target in replacements:
        value = value.replace(source, target)
    return value


def _copy_rewritten_template(
    template_root: Path,
    destination_root: Path,
    replacements: list[tuple[str, str]],
) -> None:
    for source_path in template_root.rglob("*"):
        relative_parts = [
            _replace(part, replacements)
            for part in source_path.relative_to(template_root).parts
        ]
        destination_path = destination_root.joinpath(*relative_parts)
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue
        if source_path.name == "debug.db":
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        content = source_path.read_text(encoding="utf-8")
        destination_path.write_text(_replace(content, replacements), encoding="utf-8")
