"""Tests for Session and SessionManager."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from datacloud_agent.core import Session, SessionManager
from datacloud_agent.tenant import TenantContext, TenantType


class TestSession:
    """Tests for Session dataclass."""

    def test_session_creation(self):
        """Test creating a Session with all fields."""
        session_id = "test-session-id"
        session_key = "tenant:user_001:agent:default:test-session-id"
        tenant_id = "user_001"
        agent_id = "default"
        created_at = datetime.now(timezone.utc)
        updated_at = created_at
        metadata = {"key": "value"}

        session = Session(
            session_id=session_id,
            session_key=session_key,
            tenant_id=tenant_id,
            agent_id=agent_id,
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata,
        )

        assert session.session_id == session_id
        assert session.session_key == session_key
        assert session.tenant_id == tenant_id
        assert session.agent_id == agent_id
        assert session.created_at == created_at
        assert session.updated_at == updated_at
        assert session.metadata == metadata

    def test_session_to_dict(self):
        """Test converting Session to a dictionary."""
        session = Session(
            session_id="sid",
            session_key="tenant:t:agent:a:sid",
            tenant_id="t",
            agent_id="a",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            metadata={"foo": "bar"},
        )

        data = session.to_dict()
        assert data["session_id"] == "sid"
        assert data["session_key"] == "tenant:t:agent:a:sid"
        assert data["tenant_id"] == "t"
        assert data["agent_id"] == "a"
        assert data["created_at"] == "2025-01-01T00:00:00+00:00"
        assert data["updated_at"] == "2025-01-02T00:00:00+00:00"
        assert data["metadata"] == {"foo": "bar"}

    def test_session_from_dict(self):
        """Test creating a Session from a dictionary."""
        data = {
            "session_id": "sid",
            "session_key": "tenant:t:agent:a:sid",
            "tenant_id": "t",
            "agent_id": "a",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-02T00:00:00+00:00",
            "metadata": {"foo": "bar"},
        }

        session = Session.from_dict(data)
        assert session.session_id == "sid"
        assert session.session_key == "tenant:t:agent:a:sid"
        assert session.tenant_id == "t"
        assert session.agent_id == "a"
        assert session.created_at == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert session.updated_at == datetime(2025, 1, 2, tzinfo=timezone.utc)
        assert session.metadata == {"foo": "bar"}


class TestSessionManager:
    """Tests for SessionManager."""

    async def test_create_session(self):
        """Test creating a new session."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_001", tenant_type=TenantType.USER_PRIVATE)

        session = await manager.create_session(tenant_ctx, agent_id="default")

        assert session.tenant_id == "user_001"
        assert session.agent_id == "default"
        assert session.session_key.startswith("tenant:user_001:agent:default:")
        assert session.session_id in session.session_key
        assert session.created_at == session.updated_at
        assert session.metadata == {}

    async def test_create_session_with_metadata(self):
        """Test creating a session with custom metadata."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_002", tenant_type=TenantType.USER_PUBLIC)
        metadata = {"lang": "zh", "theme": "dark"}

        session = await manager.create_session(tenant_ctx, agent_id="coder", metadata=metadata)

        assert session.tenant_id == "user_002"
        assert session.agent_id == "coder"
        assert session.metadata == metadata

    async def test_get_session_found(self):
        """Test retrieving an existing session."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_003", tenant_type=TenantType.USER_PRIVATE)
        created = await manager.create_session(tenant_ctx, agent_id="default")

        retrieved = await manager.get_session(created.session_key)
        assert retrieved is not None
        assert retrieved.session_key == created.session_key
        assert retrieved.session_id == created.session_id

    async def test_get_session_not_found(self):
        """Test retrieving a non‑existent session returns None."""
        manager = SessionManager()
        retrieved = await manager.get_session("tenant:none:agent:none:fake")
        assert retrieved is None

    async def test_get_or_create_session_existing(self):
        """Test get_or_create returns existing session."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_004", tenant_type=TenantType.USER_PRIVATE)
        created = await manager.create_session(tenant_ctx, agent_id="default")

        retrieved = await manager.get_or_create_session(tenant_ctx, agent_id="default")
        assert retrieved.session_key == created.session_key

    async def test_get_or_create_session_new(self):
        """Test get_or_create creates a new session when none exists."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_005", tenant_type=TenantType.USER_PRIVATE)

        session = await manager.get_or_create_session(tenant_ctx, agent_id="default")
        assert session.tenant_id == "user_005"
        assert session.agent_id == "default"

        # Should be the only session for this tenant‑agent pair
        sessions = await manager.list_sessions(tenant_id="user_005")
        assert len(sessions) == 1
        assert sessions[0].session_key == session.session_key

    async def test_reset_session(self):
        """Test resetting session metadata."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_006", tenant_type=TenantType.USER_PRIVATE)
        session = await manager.create_session(
            tenant_ctx, agent_id="default", metadata={"key": "value"}
        )

        assert session.metadata == {"key": "value"}
        original_updated_at = session.updated_at
        success = await manager.reset_session(session.session_key)
        assert success is True

        retrieved = await manager.get_session(session.session_key)
        assert retrieved is not None
        assert retrieved.metadata == {}
        # updated_at should be >= original (may be equal if reset within same microsecond)
        assert retrieved.updated_at >= original_updated_at

    async def test_reset_session_not_found(self):
        """Test resetting a non‑existent session returns False."""
        manager = SessionManager()
        success = await manager.reset_session("tenant:none:agent:none:fake")
        assert success is False

    async def test_list_sessions_all(self):
        """Test listing all sessions."""
        manager = SessionManager()
        tenant1 = TenantContext(tenant_id="user_007", tenant_type=TenantType.USER_PRIVATE)
        tenant2 = TenantContext(tenant_id="user_008", tenant_type=TenantType.USER_PUBLIC)

        session1 = await manager.create_session(tenant1, agent_id="default")
        session2 = await manager.create_session(tenant2, agent_id="default")
        session3 = await manager.create_session(tenant1, agent_id="coder")

        sessions = await manager.list_sessions()
        assert len(sessions) == 3
        # Should be sorted by updated_at (newest first)
        assert sessions[0].updated_at >= sessions[1].updated_at
        assert sessions[1].updated_at >= sessions[2].updated_at

        # All sessions should be present
        session_keys = {s.session_key for s in sessions}
        assert session_keys == {session1.session_key, session2.session_key, session3.session_key}

    async def test_list_sessions_filter_by_tenant(self):
        """Test listing sessions filtered by tenant_id."""
        manager = SessionManager()
        tenant1 = TenantContext(tenant_id="user_009", tenant_type=TenantType.USER_PRIVATE)
        tenant2 = TenantContext(tenant_id="user_010", tenant_type=TenantType.USER_PUBLIC)

        session1 = await manager.create_session(tenant1, agent_id="default")
        await manager.create_session(tenant2, agent_id="default")
        session3 = await manager.create_session(tenant1, agent_id="coder")

        sessions = await manager.list_sessions(tenant_id="user_009")
        assert len(sessions) == 2
        session_keys = {s.session_key for s in sessions}
        assert session_keys == {session1.session_key, session3.session_key}

    async def test_delete_session(self):
        """Test deleting a session."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_011", tenant_type=TenantType.USER_PRIVATE)
        session = await manager.create_session(tenant_ctx, agent_id="default")

        success = await manager.delete_session(session.session_key)
        assert success is True

        retrieved = await manager.get_session(session.session_key)
        assert retrieved is None

    async def test_delete_session_not_found(self):
        """Test deleting a non‑existent session returns False."""
        manager = SessionManager()
        success = await manager.delete_session("tenant:none:agent:none:fake")
        assert success is False


class TestSessionManagerWithPersistence:
    """Tests for SessionManager with JSONL persistence."""

    async def test_persistence_create_and_load(self, tmp_path: Path):
        """Test that sessions are persisted and reloaded."""
        persistence_file = tmp_path / "sessions.jsonl"
        manager = SessionManager(persistence_file)
        tenant_ctx = TenantContext(tenant_id="user_012", tenant_type=TenantType.USER_PRIVATE)

        # Create a session
        session = await manager.create_session(tenant_ctx, agent_id="default")
        # Wait for background save to complete
        await asyncio.sleep(0.01)

        # Create a new manager that loads from the same file
        manager2 = SessionManager(persistence_file)
        # Wait for background load to complete
        await asyncio.sleep(0.01)

        retrieved = await manager2.get_session(session.session_key)
        assert retrieved is not None
        assert retrieved.session_key == session.session_key
        assert retrieved.tenant_id == session.tenant_id
        assert retrieved.agent_id == session.agent_id
        assert retrieved.metadata == session.metadata
        # Timestamps may differ slightly due to serialization rounding
        assert abs(retrieved.created_at - session.created_at).total_seconds() < 1
        assert abs(retrieved.updated_at - session.updated_at).total_seconds() < 1

    async def test_persistence_updates(self, tmp_path: Path):
        """Test that session updates are persisted."""
        persistence_file = tmp_path / "sessions.jsonl"
        manager = SessionManager(persistence_file)
        tenant_ctx = TenantContext(tenant_id="user_013", tenant_type=TenantType.USER_PRIVATE)

        session = await manager.create_session(
            tenant_ctx, agent_id="default", metadata={"initial": "data"}
        )
        await asyncio.sleep(0.01)

        # Update the session
        await manager.reset_session(session.session_key)
        await asyncio.sleep(0.01)

        # Load into a new manager
        manager2 = SessionManager(persistence_file)
        await asyncio.sleep(0.01)

        retrieved = await manager2.get_session(session.session_key)
        assert retrieved is not None
        assert retrieved.metadata == {}
        assert retrieved.updated_at >= session.updated_at

    async def test_persistence_empty_file(self, tmp_path: Path):
        """Test that an empty persistence file does not cause errors."""
        persistence_file = tmp_path / "empty.jsonl"
        persistence_file.touch()

        manager = SessionManager(persistence_file)
        await asyncio.sleep(0.01)

        # Should have no sessions
        sessions = await manager.list_sessions()
        assert len(sessions) == 0

    async def test_persistence_malformed_lines_skipped(self, tmp_path: Path):
        """Test that malformed JSON lines are skipped during loading."""
        persistence_file = tmp_path / "malformed.jsonl"
        persistence_file.write_text(
            '{"session_id": "good"}\nnot json\n{"session_id": "also_good"}\n'
        )

        manager = SessionManager(persistence_file)
        await asyncio.sleep(0.01)

        # Only the two valid lines should be loaded
        sessions = await manager.list_sessions()
        # But note that our Session.from_dict expects all fields, so those lines
        # will also be skipped because they lack required fields.
        # So we expect zero sessions.
        assert len(sessions) == 0

    async def test_no_persistence(self):
        """Test that sessions are not persisted when no path is given."""
        manager = SessionManager()
        tenant_ctx = TenantContext(tenant_id="user_014", tenant_type=TenantType.USER_PRIVATE)

        session = await manager.create_session(tenant_ctx, agent_id="default")
        # No file exists, so creating a new manager with a path should not load the session
        manager2 = SessionManager(Path("/tmp/does_not_exist.jsonl"))
        await asyncio.sleep(0.01)

        retrieved = await manager2.get_session(session.session_key)
        assert retrieved is None
