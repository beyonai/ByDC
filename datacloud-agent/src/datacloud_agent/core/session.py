"""Session management for OpenClaw Gateway.

Provides Session dataclass and SessionManager class for managing agent sessions
with optional JSONL persistence.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datacloud_agent.tenant.context import TenantContext


@dataclass
class Session:
    """Session data for an agent within a tenant.

    Attributes:
        session_id: Unique session identifier (UUID).
        session_key: Full session key in format
            `tenant:{tenant_id}:agent:{agent_id}:{session_id}`.
        tenant_id: Tenant identifier.
        agent_id: Agent identifier.
        created_at: Timestamp when session was created.
        updated_at: Timestamp when session was last updated.
        metadata: Optional extra data for the session.
    """

    session_id: str
    session_key: str
    tenant_id: str
    agent_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert session to a JSON‑serializable dictionary."""
        data = asdict(self)
        # Convert datetime objects to ISO‑format strings
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Create a Session from a dictionary (e.g., loaded from JSON)."""
        # Convert ISO strings back to datetime objects
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


class SessionManager:
    """Manager for agent sessions with optional JSONL persistence.

    Args:
        persistence_path: If provided, sessions are loaded from and saved to
            this JSONL file. Each line is a JSON‑encoded Session.
    """

    def __init__(self, persistence_path: Path | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._persistence_path = Path(persistence_path) if persistence_path else None
        self._load_lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()

        # Load existing sessions if persistence file exists
        if self._persistence_path and self._persistence_path.exists():
            asyncio.create_task(self._load_sessions())

    async def _load_sessions(self) -> None:
        """Load sessions from the persistence file (background)."""
        if self._persistence_path is None:
            return
        async with self._load_lock:
            try:
                content = await asyncio.to_thread(
                    self._persistence_path.read_text, encoding="utf-8"
                )
            except FileNotFoundError:
                return
            except OSError:
                # If the file cannot be read, start with empty sessions
                return

            for line in content.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    session = Session.from_dict(data)
                    self._sessions[session.session_key] = session
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Skip malformed lines
                    continue

    async def _save_session(self, session: Session) -> None:
        """Append a session to the persistence file (background)."""
        if not self._persistence_path:
            return

        async with self._save_lock:
            line = json.dumps(session.to_dict(), ensure_ascii=False) + "\n"
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        """Thread‑safe helper to append a line to the persistence file."""
        assert self._persistence_path is not None
        with self._persistence_path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def create_session(
        self,
        tenant_ctx: TenantContext,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new session for the given tenant and agent.

        Args:
            tenant_ctx: Tenant context.
            agent_id: Agent identifier.
            metadata: Optional extra data for the session.
            session_id: Optional session ID. If not provided, a new UUID will be generated.

        Returns:
            The created Session.
        """
        session_id = session_id or str(uuid.uuid4())
        session_key = f"tenant:{tenant_ctx.tenant_id}:agent:{agent_id}:{session_id}"
        now = datetime.now(UTC)

        session = Session(
            session_id=session_id,
            session_key=session_key,
            tenant_id=tenant_ctx.tenant_id,
            agent_id=agent_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        self._sessions[session_key] = session
        asyncio.create_task(self._save_session(session))
        return session

    async def get_session(self, session_key: str) -> Session | None:
        """Retrieve a session by its key.

        Args:
            session_key: Full session key.

        Returns:
            The Session if found, None otherwise.
        """
        return self._sessions.get(session_key)

    async def get_or_create_session(
        self,
        tenant_ctx: TenantContext,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Get an existing session or create a new one.

        Looks for a session with the same tenant and agent. If multiple exist,
        returns the most recently updated one.

        Args:
            tenant_ctx: Tenant context.
            agent_id: Agent identifier.
            metadata: Optional extra data for the session (used only if creating).

        Returns:
            The existing or newly created Session.
        """
        # Build a pattern to match session keys for this tenant‑agent pair
        prefix = f"tenant:{tenant_ctx.tenant_id}:agent:{agent_id}:"
        matching = [session for key, session in self._sessions.items() if key.startswith(prefix)]

        if matching:
            # Return the most recently updated session
            matching.sort(key=lambda s: s.updated_at, reverse=True)
            return matching[0]

        # No existing session → create one
        return await self.create_session(tenant_ctx, agent_id, metadata)

    async def reset_session(self, session_key: str) -> bool:
        """Clear session data (metadata) while keeping the session alive.

        Args:
            session_key: Full session key.

        Returns:
            True if the session was found and reset, False otherwise.
        """
        session = self._sessions.get(session_key)
        if session is None:
            return False

        session.metadata.clear()
        session.updated_at = datetime.now(UTC)
        asyncio.create_task(self._save_session(session))
        return True

    async def list_sessions(self, tenant_id: str | None = None) -> list[Session]:
        """List all sessions, optionally filtered by tenant.

        Args:
            tenant_id: If provided, only return sessions for this tenant.

        Returns:
            List of Session objects, sorted by updated_at (newest first).
        """
        sessions = list(self._sessions.values())
        if tenant_id is not None:
            sessions = [s for s in sessions if s.tenant_id == tenant_id]

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    async def delete_session(self, session_key: str) -> bool:
        """Delete a session.

        Args:
            session_key: Full session key.

        Returns:
            True if the session was found and deleted, False otherwise.
        """
        if session_key not in self._sessions:
            return False

        del self._sessions[session_key]
        # Note: persistence file is append‑only, so we cannot remove the line.
        # To fully delete from persistence, we would need to rewrite the file,
        # which is out of scope for this simple implementation.
        return True
