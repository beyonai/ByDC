"""Tests for backend module."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from datacloud_analysis.backend import SessionStore, TenantAwareFileBackend
from datacloud_analysis.tenant import TenantContext, TenantType


class TestTenantAwareFileBackend:
    """Tests for TenantAwareFileBackend."""

    def test_get_full_path_public(self, tmp_path: Path):
        """Public prefix does not require tenant context."""
        backend = TenantAwareFileBackend(tmp_path)
        full = backend.get_full_path("public/test.txt")
        assert full == tmp_path / "public/test.txt"
        # Should not raise

    def test_get_full_path_public_with_tenant_context(self, tmp_path: Path):
        """Public prefix ignores tenant context even if present."""
        ctx = TenantContext(tenant_id="user_123", tenant_type=TenantType.USER_PRIVATE)
        token = ctx.scoped()
        try:
            backend = TenantAwareFileBackend(tmp_path)
            full = backend.get_full_path("public/foo.txt")
            assert full == tmp_path / "public/foo.txt"
        finally:
            TenantContext.reset(token)

    def test_get_full_path_user_prefix_without_context(self, tmp_path: Path):
        """User prefixes require tenant context."""
        backend = TenantAwareFileBackend(tmp_path)
        with pytest.raises(ValueError, match="requires a tenant context"):
            backend.get_full_path("user_private/file.txt")
        with pytest.raises(ValueError, match="requires a tenant context"):
            backend.get_full_path("user_public/file.txt")

    def test_get_full_path_user_prefix_with_context(self, tmp_path: Path):
        """User prefixes insert tenant ID."""
        ctx = TenantContext(tenant_id="user_123", tenant_type=TenantType.USER_PRIVATE)
        token = ctx.scoped()
        try:
            backend = TenantAwareFileBackend(tmp_path)
            full = backend.get_full_path("user_private/doc.txt")
            assert full == tmp_path / "user_private/user_123/doc.txt"
            full = backend.get_full_path("user_public/image.jpg")
            assert full == tmp_path / "user_public/user_123/image.jpg"
        finally:
            TenantContext.reset(token)

    def test_get_full_path_invalid_prefix(self, tmp_path: Path):
        """Invalid prefix raises ValueError."""
        backend = TenantAwareFileBackend(tmp_path)
        with pytest.raises(ValueError, match="must start with"):
            backend.get_full_path("invalid/foo.txt")
        with pytest.raises(ValueError, match="must start with"):
            backend.get_full_path("")

    @pytest.mark.asyncio
    async def test_write_read_public(self, tmp_path: Path):
        """Write and read a public file."""
        backend = TenantAwareFileBackend(tmp_path)
        content = b"hello world"
        await backend.write("public/test.txt", content)
        assert await backend.exists("public/test.txt") is True
        read_content = await backend.read("public/test.txt")
        assert read_content == content

    @pytest.mark.asyncio
    async def test_write_read_user_prefix(self, tmp_path: Path):
        """Write and read a tenant‑isolated file."""
        ctx = TenantContext(tenant_id="user_123", tenant_type=TenantType.USER_PRIVATE)
        token = ctx.scoped()
        try:
            backend = TenantAwareFileBackend(tmp_path)
            content = b"private data"
            await backend.write("user_private/secret.txt", content)
            # Verify the file is placed under tenant subdirectory
            expected_path = tmp_path / "user_private/user_123/secret.txt"
            assert expected_path.exists()
            assert await backend.exists("user_private/secret.txt") is True
            read_content = await backend.read("user_private/secret.txt")
            assert read_content == content
        finally:
            TenantContext.reset(token)

    @pytest.mark.asyncio
    async def test_exists_false(self, tmp_path: Path):
        """Exists returns False for missing file."""
        backend = TenantAwareFileBackend(tmp_path)
        exists = await backend.exists("public/nonexistent.txt")
        assert exists is False

    @pytest.mark.asyncio
    async def test_list_dir(self, tmp_path: Path):
        """List directory contents."""
        backend = TenantAwareFileBackend(tmp_path)
        # Create a few files in a public subdirectory
        await backend.write("public/subdir/a.txt", b"a")
        await backend.write("public/subdir/b.txt", b"b")
        await backend.write("public/subdir/c.txt", b"c")
        entries = await backend.list_dir("public/subdir")
        assert set(entries) == {"a.txt", "b.txt", "c.txt"}
        # List empty directory
        entries = await backend.list_dir("public/empty")
        assert entries == []

    @pytest.mark.asyncio
    async def test_list_dir_not_a_directory(self, tmp_path: Path):
        """Listing a file raises NotADirectoryError."""
        backend = TenantAwareFileBackend(tmp_path)
        await backend.write("public/file.txt", b"content")
        with pytest.raises(NotADirectoryError):
            await backend.list_dir("public/file.txt")


class TestSessionStore:
    """Tests for SessionStore."""

    @pytest.mark.asyncio
    async def test_append_read(self, tmp_path: Path):
        """Append records and read them back."""
        store = SessionStore(tmp_path)
        records = [
            {"type": "message", "content": "hello"},
            {"type": "action", "action": "click"},
            {"type": "message", "content": "world"},
        ]
        for rec in records:
            await store.append("session-1", rec)
        # Read all
        read = await store.read("session-1")
        assert read == records
        # Read with limit
        read = await store.read("session-1", limit=2)
        assert read == records[:2]
        # Read with limit larger than total
        read = await store.read("session-1", limit=100)
        assert read == records
        # Read with limit=0
        read = await store.read("session-1", limit=0)
        assert read == []

    @pytest.mark.asyncio
    async def test_read_empty_or_missing(self, tmp_path: Path):
        """Reading a missing session returns empty list."""
        store = SessionStore(tmp_path)
        assert await store.read("nonexistent") == []
        # Create an empty file
        path = tmp_path / "sessions" / "empty.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        assert await store.read("empty") == []

    @pytest.mark.asyncio
    async def test_append_malformed_line_skipped(self, tmp_path: Path):
        """Malformed JSON lines are skipped."""
        store = SessionStore(tmp_path)
        path = tmp_path / "sessions" / "bad.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write('{"valid": 1}\n')
            f.write("invalid json\n")
            f.write('{"valid": 2}\n')
        read = await store.read("bad")
        assert read == [{"valid": 1}, {"valid": 2}]

    @pytest.mark.asyncio
    async def test_read_since(self, tmp_path: Path):
        """Filter records by timestamp."""
        store = SessionStore(tmp_path)
        base = datetime(2025, 1, 1, 12, 0, 0)
        records = [
            {"timestamp": (base + timedelta(minutes=i)).isoformat(), "value": i} for i in range(5)
        ]
        for rec in records:
            await store.append("session-ts", rec)
        # Read since base + 2 minutes (inclusive)
        since = base + timedelta(minutes=2)
        filtered = await store.read_since("session-ts", since)
        assert len(filtered) == 3  # minutes 2,3,4
        assert [r["value"] for r in filtered] == [2, 3, 4]
        # Since far in the future
        future = base + timedelta(days=1)
        filtered = await store.read_since("session-ts", future)
        assert filtered == []
        # Since before any record
        past = base - timedelta(days=1)
        filtered = await store.read_since("session-ts", past)
        assert len(filtered) == 5

    @pytest.mark.asyncio
    async def test_read_since_no_timestamp(self, tmp_path: Path):
        """Records without timestamp are ignored."""
        store = SessionStore(tmp_path)
        records = [
            {"data": "no timestamp"},
            {"timestamp": "2025-01-01T12:00:00", "data": "with timestamp"},
            {"data": "also no timestamp"},
        ]
        for rec in records:
            await store.append("session-no-ts", rec)
        filtered = await store.read_since("session-no-ts", datetime.min)
        # Only the record with timestamp is returned
        assert len(filtered) == 1
        assert filtered[0]["data"] == "with timestamp"

    @pytest.mark.asyncio
    async def test_clear(self, tmp_path: Path):
        """Clear deletes the session file."""
        store = SessionStore(tmp_path)
        await store.append("session-1", {"test": 1})
        path = tmp_path / "sessions" / "session-1.jsonl"
        assert path.exists()
        await store.clear("session-1")
        assert not path.exists()
        # Clearing again should not raise (missing_ok=True)
        await store.clear("session-1")

    @pytest.mark.asyncio
    async def test_invalid_session_id(self, tmp_path: Path):
        """Invalid session IDs raise ValueError."""
        store = SessionStore(tmp_path)
        with pytest.raises(ValueError, match="Invalid session_id"):
            await store.append("../evil", {})
        with pytest.raises(ValueError, match="Invalid session_id"):
            await store.read("../../etc/passwd")
        with pytest.raises(ValueError, match="Invalid session_id"):
            await store.clear("foo/bar")
