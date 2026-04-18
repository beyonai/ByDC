"""Local persistent result-file storage implementation."""

from __future__ import annotations

from pathlib import Path

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.file_storage.base import ResultFileStorage
from datacloud_data_sdk.file_storage.scoped_paths import (
    normalize_logical_file_path,
    sanitize_path_segment,
    shared_workspace_dir,
)


class LocalResultFileStorage(ResultFileStorage):
    """Store exported result files under a scoped local directory."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)

    @property
    def storage_type(self) -> str:
        return "local"

    def write_text(self, file_path: str, content: str) -> str:
        actual_path = self.resolve_path(file_path)
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        actual_path.write_text(content, encoding="utf-8")
        return file_path

    def append_text(self, file_path: str, content: str) -> str:
        actual_path = self.resolve_path(file_path)
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        with actual_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(content)
        return file_path

    def read_text(self, file_path: str, begin_line: int = 0, end_line: int = -1) -> str | None:
        actual_path = self.resolve_path(file_path)
        if not actual_path.exists():
            return None
        content = actual_path.read_text(encoding="utf-8")
        if begin_line <= 0 and end_line < 0:
            return content
        lines = content.splitlines()
        start = max(begin_line, 0)
        stop = len(lines) if end_line < 0 else min(end_line, len(lines))
        return "\n".join(lines[start:stop])

    def resolve_path(self, file_path: str) -> Path:
        logical_path = normalize_logical_file_path(file_path)
        relative_parts = logical_path.relative_to("/").parts
        return self._effective_base_dir().joinpath(*relative_parts)

    def _effective_base_dir(self) -> Path:
        try:
            ctx = get_current_context()
        except Exception:
            return self._base_dir

        base_dir = self._base_dir
        workspace_dir = str(getattr(ctx, "workspace_dir", "") or "").strip()
        if workspace_dir:
            base_dir = shared_workspace_dir(Path(workspace_dir))

        user_id = sanitize_path_segment(str(getattr(ctx, "user_id", "") or ""))
        session_id = sanitize_path_segment(str(getattr(ctx, "session_id", "") or ""))
        if user_id and session_id:
            return base_dir / user_id / "sessions" / session_id
        return base_dir
