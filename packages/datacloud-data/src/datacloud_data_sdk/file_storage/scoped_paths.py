"""Shared path helpers for request-scoped local storage."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def sanitize_path_segment(value: str) -> str:
    """Sanitize a single path segment to avoid invalid or unsafe separators."""
    return value.replace(":", "_").replace("\\", "_").replace("/", "_").strip()


def shared_workspace_dir(workspace_dir: Path) -> Path:
    """Normalize to the nearest shared ``private/public`` workspace root."""
    resolved = workspace_dir.resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name in {"private", "public"}:
            return candidate
    return resolved


def normalize_logical_file_path(file_path: str) -> PurePosixPath:
    """Normalize a logical storage path and reject traversal."""
    normalized = PurePosixPath(file_path if file_path.startswith("/") else f"/{file_path}")
    if ".." in normalized.parts:
        raise ValueError(f"invalid file path: {file_path}")
    return normalized
