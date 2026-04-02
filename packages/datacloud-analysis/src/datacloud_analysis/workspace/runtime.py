from __future__ import annotations

import os
from pathlib import Path, PurePath, PurePosixPath

_SHARED_WORKSPACE_MARKERS = {"private", "public"}


def resolve_shared_workspace_dir(workspace_dir: str | Path | None) -> Path | PurePath | None:
    """Normalize a workspace path to the shared private/public root when present."""
    if workspace_dir is None:
        return None

    # Keep POSIX-style absolute paths stable on Windows for tests and cross-platform inputs.
    if isinstance(workspace_dir, str) and os.name == "nt" and workspace_dir.startswith("/"):
        resolved: PurePath = PurePosixPath(workspace_dir)
    else:
        resolved = Path(workspace_dir).resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name in _SHARED_WORKSPACE_MARKERS:
            return candidate
    return resolved
