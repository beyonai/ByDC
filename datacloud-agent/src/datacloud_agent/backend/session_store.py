"""JSONL-based session persistence."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionStore:
    """Append‑only session store using JSONL (one JSON object per line) files.

    Files are stored under `{base_dir}/sessions/{session_id}.jsonl`.

    Args:
        base_dir: Root directory for session storage.
    """

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.sessions_dir = self.base_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Return the absolute path for a session file."""
        # Sanitize session_id to prevent directory traversal
        if "/" in session_id or "\\" in session_id:
            raise ValueError(f"Invalid session_id: {session_id}")
        return self.sessions_dir / f"{session_id}.jsonl"

    async def append(self, session_id: str, record: dict[str, Any]) -> None:
        """Append a record to the session file.

        The record is serialized as a JSON object and written as a single line.

        Args:
            session_id: Session identifier.
            record: Dictionary to store.
        """
        path = self._session_path(session_id)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        await asyncio.to_thread(self._append_line, path, line)

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        """Thread‑safe helper to append a line to a file."""
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def read(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Read records from a session file.

        Args:
            session_id: Session identifier.
            limit: Maximum number of records to return (None means all).

        Returns:
            List of records, in the order they were written.
        """
        path = self._session_path(session_id)
        if not await asyncio.to_thread(path.exists):
            return []
        lines = await asyncio.to_thread(self._read_lines, path, limit)
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines (should not happen in normal operation)
                continue
        return records

    @staticmethod
    def _read_lines(path: Path, limit: int | None) -> list[str]:
        """Thread‑safe helper to read lines from a file."""
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if limit is not None and limit >= 0:
            lines = lines[:limit]
        return lines

    async def read_since(self, session_id: str, since: datetime) -> list[dict[str, Any]]:
        """Read records written after a given timestamp.

        This implementation assumes each record contains a `timestamp` field
        (ISO‑formatted string). If a record does not have a timestamp, it is
        ignored.

        Args:
            session_id: Session identifier.
            since: Minimum timestamp (inclusive).

        Returns:
            List of records whose timestamp is >= `since`.
        """
        all_records = await self.read(session_id)
        filtered = []
        for rec in all_records:
            ts_str = rec.get("timestamp")
            if ts_str is None:
                continue
            try:
                # Try to parse as ISO‑format datetime
                ts = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                continue
            if ts >= since:
                filtered.append(rec)
        return filtered

    async def clear(self, session_id: str) -> None:
        """Delete the session file.

        Args:
            session_id: Session identifier.
        """
        path = self._session_path(session_id)
        await asyncio.to_thread(path.unlink, missing_ok=True)
