from __future__ import annotations

from pathlib import Path

_SHARED_WORKSPACE_MARKERS = {"private", "public"}


def resolve_shared_workspace_dir(workspace_dir: str | Path | None) -> Path | None:
    """Normalize a workspace path to the shared private/public root when present."""
    if workspace_dir is None:
        return None

    resolved = Path(workspace_dir).resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name in _SHARED_WORKSPACE_MARKERS:
            return candidate
    return resolved
