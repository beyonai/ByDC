"""Tests for tenant module."""

import asyncio

import pytest

from datacloud_analysis.tenant import TenantContext, TenantResolver, TenantType, tenant_ctx


class TestTenantType:
    """Tests for TenantType enum."""

    def test_tenant_types(self):
        """Test all tenant types exist."""
        assert TenantType.USER_PRIVATE.value == "user_private"
        assert TenantType.USER_PUBLIC.value == "user_public"
        assert TenantType.PUBLIC.value == "public"


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_basic_context(self):
        """Test basic context creation."""
        ctx = TenantContext(
            tenant_id="user_001",
            tenant_type=TenantType.USER_PRIVATE,
        )
        assert ctx.tenant_id == "user_001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE
        assert ctx.session_id is None
        assert ctx.task_id is None
        assert ctx.metadata == {}

    def test_full_context(self):
        """Test context with all fields."""
        ctx = TenantContext(
            tenant_id="user_001",
            tenant_type=TenantType.USER_PRIVATE,
            session_id="sess_123",
            task_id="task_456",
            metadata={"key": "value"},
        )
        assert ctx.session_id == "sess_123"
        assert ctx.task_id == "task_456"
        assert ctx.metadata == {"key": "value"}

    def test_path_prefix_user_private(self):
        """Test path prefix for USER_PRIVATE."""
        ctx = TenantContext(
            tenant_id="user_001",
            tenant_type=TenantType.USER_PRIVATE,
        )
        assert ctx.get_path_prefix() == "user_private/user_001"

    def test_path_prefix_user_public(self):
        """Test path prefix for USER_PUBLIC."""
        ctx = TenantContext(
            tenant_id="org_001",
            tenant_type=TenantType.USER_PUBLIC,
        )
        assert ctx.get_path_prefix() == "user_public/org_001"

    def test_path_prefix_public(self):
        """Test path prefix for PUBLIC."""
        ctx = TenantContext(
            tenant_id="public",
            tenant_type=TenantType.PUBLIC,
        )
        assert ctx.get_path_prefix() == "public/public"

    def test_scoped_and_reset(self):
        """Test context scoping and reset."""
        ctx = TenantContext(
            tenant_id="test_user",
            tenant_type=TenantType.USER_PRIVATE,
        )
        token = ctx.scoped()
        assert tenant_ctx.get() == ctx
        TenantContext.reset(token)
        assert tenant_ctx.get() is None

    def test_get_current_none(self):
        """Test get_current when no context is set."""
        # Ensure no context is set
        tenant_ctx.set(None)
        assert TenantContext.get_current() is None

    def test_get_current_with_context(self):
        """Test get_current when context is set."""
        ctx = TenantContext(
            tenant_id="test_user",
            tenant_type=TenantType.USER_PRIVATE,
        )
        token = ctx.scoped()
        try:
            result = TenantContext.get_current()
            assert result == ctx
            assert result.tenant_id == "test_user"
        finally:
            TenantContext.reset(token)


class TestAsyncContextIsolation:
    """Tests for async context isolation."""

    @pytest.mark.asyncio
    async def test_context_isolation_asyncio(self):
        """Test context isolation between concurrent async tasks."""

        async def task1():
            token = TenantContext(
                tenant_id="A",
                tenant_type=TenantType.USER_PRIVATE,
            ).scoped()
            await asyncio.sleep(0.1)
            result = tenant_ctx.get().tenant_id
            TenantContext.reset(token)
            return result

        async def task2():
            token = TenantContext(
                tenant_id="B",
                tenant_type=TenantType.USER_PRIVATE,
            ).scoped()
            await asyncio.sleep(0.05)
            result = tenant_ctx.get().tenant_id
            TenantContext.reset(token)
            return result

        results = await asyncio.gather(task1(), task2())
        assert list(results) == ["A", "B"]

    @pytest.mark.asyncio
    async def test_nested_async_contexts(self):
        """Test nested async contexts maintain proper isolation."""

        async def inner_task(expected_id: str):
            await asyncio.sleep(0.01)
            current = tenant_ctx.get()
            assert current is not None
            assert current.tenant_id == expected_id
            return current.tenant_id

        async def outer_task(tenant_id: str):
            ctx = TenantContext(
                tenant_id=tenant_id,
                tenant_type=TenantType.USER_PRIVATE,
            )
            token = ctx.scoped()
            try:
                result = await inner_task(tenant_id)
                return result
            finally:
                TenantContext.reset(token)

        results = await asyncio.gather(
            outer_task("user_1"),
            outer_task("user_2"),
            outer_task("user_3"),
        )
        assert results == ["user_1", "user_2", "user_3"]


class TestTenantResolver:
    """Tests for TenantResolver."""

    def test_resolve_from_path_user_private(self):
        """Test resolving tenant from private user path."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_path("user_private/user_001/file.txt")

        assert ctx.tenant_id == "user_001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE

    def test_resolve_from_path_user_public(self):
        """Test resolving tenant from public user path."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_path("user_public/org_001/data.csv")

        assert ctx.tenant_id == "org_001"
        assert ctx.tenant_type == TenantType.USER_PUBLIC

    def test_resolve_from_path_public(self):
        """Test resolving tenant from public path."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_path("public/readme.md")

        assert ctx.tenant_id == "public"
        assert ctx.tenant_type == TenantType.PUBLIC

    def test_resolve_from_path_invalid_type(self):
        """Test resolving with invalid tenant type."""
        resolver = TenantResolver()
        with pytest.raises(ValueError, match="Unknown tenant type"):
            resolver.resolve_from_path("invalid_type/user_001/file.txt")

    def test_resolve_from_path_missing_tenant_id(self):
        """Test resolving with missing tenant_id."""
        resolver = TenantResolver()
        with pytest.raises(ValueError, match="Missing tenant_id"):
            resolver.resolve_from_path("user_private")

    def test_resolve_from_session_user_private(self):
        """Test resolving tenant from private user session."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("user_private_user001_sess123")

        assert ctx.tenant_id == "user001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE
        assert ctx.session_id == "sess123"

    def test_resolve_from_session_user_public(self):
        """Test resolving tenant from public user session."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("user_public_org001_session456")

        assert ctx.tenant_id == "org001"
        assert ctx.tenant_type == TenantType.USER_PUBLIC
        assert ctx.session_id == "session456"

    def test_resolve_from_session_public(self):
        """Test resolving tenant from public session."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("public_session789")

        assert ctx.tenant_id == "public"
        assert ctx.tenant_type == TenantType.PUBLIC
        assert ctx.session_id == "session789"

    def test_resolve_from_session_invalid(self):
        """Test resolving from invalid session key defaults to public."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("invalid_key")

        assert ctx.tenant_id == "public"
        assert ctx.tenant_type == TenantType.PUBLIC
        assert ctx.session_id == "invalid_key"

    def test_resolve_from_session_new_colon_format(self):
        """Test resolving tenant from new colon-separated session key format."""
        resolver = TenantResolver()
        # Format: tenant:{tenant_id}:agent:{agent_id}:{session_id}
        ctx = resolver.resolve_from_session("tenant:user001:agent:default:session123")

        assert ctx.tenant_id == "user001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE
        assert ctx.session_id == "session123"

    def test_resolve_from_session_new_colon_format_public(self):
        """Test resolving tenant from new format with public tenant."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("tenant:public:agent:default:session456")

        assert ctx.tenant_id == "public"
        assert ctx.tenant_type == TenantType.PUBLIC
        assert ctx.session_id == "session456"

    def test_resolve_from_session_new_format_complex_session_id(self):
        """Test resolving tenant from new format with complex session ID."""
        resolver = TenantResolver()
        # Session ID can contain colons
        ctx = resolver.resolve_from_session("tenant:user001:agent:default:session:123:abc")

        assert ctx.tenant_id == "user001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE
        assert ctx.session_id == "session:123:abc"

    def test_resolve_from_session_fallback_to_legacy(self):
        """Test that legacy format still works as fallback."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("user_private_user001_sess123")

        assert ctx.tenant_id == "user001"
        assert ctx.tenant_type == TenantType.USER_PRIVATE
        assert ctx.session_id == "sess123"

    def test_resolve_from_session_unknown_format_defaults_to_public(self):
        """Test that unknown format defaults to public tenant."""
        resolver = TenantResolver()
        ctx = resolver.resolve_from_session("totally_invalid_key")

        assert ctx.tenant_id == "public"
        assert ctx.tenant_type == TenantType.PUBLIC
        assert ctx.session_id == "totally_invalid_key"
