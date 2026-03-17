"""Tests for AgentRegistry deepagents functionality."""

import pytest

from datacloud_analysis.core import AgentConfig, AgentRegistry


class TestAgentConfigDeepAgents:
    """Tests for AgentConfig dataclass with deepagents fields."""

    def test_agent_config_creation(self):
        """Test creating an AgentConfig with required fields."""
        config = AgentConfig(
            agent_id="test-agent",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        assert config.agent_id == "test-agent"
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.system_prompt is None
        assert config.tools == []
        assert config.subagents == []

    def test_agent_config_with_optional_fields(self):
        """Test AgentConfig with optional fields."""
        subagents = [
            {"name": "researcher", "description": "Research agent"},
            {"name": "data_analyst", "description": "Data analyst agent"},
        ]
        config = AgentConfig(
            agent_id="test-agent",
            provider="openai",
            model="gpt-4",
            system_prompt="You are a helpful assistant.",
            tools=["know", "query", "compute"],
            subagents=subagents,
        )
        assert config.agent_id == "test-agent"
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.system_prompt == "You are a helpful assistant."
        assert config.tools == ["know", "query", "compute"]
        assert config.subagents == subagents


class TestAgentRegistryDeepAgents:
    """Tests for AgentRegistry with deepagents functionality."""

    def test_agent_registry_register_and_get(self):
        """Test registering and retrieving an agent."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        registry.register("default", config)
        retrieved = registry.get("default")
        assert retrieved is not None
        assert retrieved.agent_id == "default"
        assert retrieved.provider == "anthropic"
        assert retrieved.model == "claude-sonnet-4-20250514"

    def test_agent_registry_list(self):
        """Test listing agents returns correct structure."""
        registry = AgentRegistry()
        config1 = AgentConfig(
            agent_id="agent1",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        config2 = AgentConfig(
            agent_id="agent2",
            provider="openai",
            model="gpt-4",
        )
        registry.register("agent1", config1)
        registry.register("agent2", config2)

        agents = registry.list_agents()
        assert len(agents) == 2
        agent_ids = {a["id"] for a in agents}
        assert agent_ids == {"agent1", "agent2"}

        for agent in agents:
            if agent["id"] == "agent1":
                assert agent["provider"] == "anthropic"
                assert agent["model"] == "claude-sonnet-4-20250514"
            else:
                assert agent["provider"] == "openai"
                assert agent["model"] == "gpt-4"


class TestCreateDefaultAgent:
    """Tests for create_default_agent method."""

    def test_create_default_agent(self):
        """Test creating a default agent with default subagents and tools."""
        registry = AgentRegistry()
        config = registry.create_default_agent("default-agent")

        assert config.agent_id == "default-agent"
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.system_prompt is not None
        # Should have 5 business tools: know, query, compute, render, store
        assert len(config.tools) == 5
        assert "know" in config.tools
        assert "query" in config.tools
        assert "compute" in config.tools
        assert "render" in config.tools
        assert "store" in config.tools
        # Should have 3 default subagents: researcher, data_analyst, visualizer
        assert len(config.subagents) == 3
        subagent_names = [sa["name"] for sa in config.subagents]
        assert "researcher" in subagent_names
        assert "data_analyst" in subagent_names
        assert "visualizer" in subagent_names

    def test_create_default_agent_custom(self):
        """Test creating default agent with custom provider and model."""
        registry = AgentRegistry()
        config = registry.create_default_agent(
            "custom-agent",
            provider="openai",
            model="gpt-4-turbo",
        )

        assert config.agent_id == "custom-agent"
        assert config.provider == "openai"
        assert config.model == "gpt-4-turbo"


class TestTenantIdValidation:
    """Tests for tenant ID validation."""

    def test_tenant_id_validation_valid(self):
        """Test valid tenant IDs pass validation."""
        registry = AgentRegistry()

        # Should not raise
        registry._validate_tenant_id("tenant123")
        registry._validate_tenant_id("my_tenant")
        registry._validate_tenant_id("tenant-name")
        registry._validate_tenant_id("abc")
        registry._validate_tenant_id("a" * 64)

    def test_tenant_id_validation_invalid_short(self):
        """Test tenant IDs that are too short raise ValueError."""
        registry = AgentRegistry()

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("ab")

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("a")

    def test_tenant_id_validation_invalid_chars(self):
        """Test tenant IDs with invalid characters raise ValueError."""
        registry = AgentRegistry()

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("Tenant123")  # uppercase

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("tenant 123")  # space

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("tenant@123")  # @ symbol

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("tenant.123")  # dot

    def test_tenant_id_validation_invalid_long(self):
        """Test tenant IDs that are too long raise ValueError."""
        registry = AgentRegistry()

        with pytest.raises(ValueError, match="Invalid tenant_id"):
            registry._validate_tenant_id("a" * 65)


class TestTenantAccessControl:
    """Tests for tenant access control."""

    def test_tenant_access_control_allowed(self):
        """Test tenant can access when in allowed_tenants list."""
        registry = AgentRegistry(allowed_tenants=["tenant1", "tenant2"])

        # Should not raise
        registry._check_tenant_access("tenant1")
        registry._check_tenant_access("tenant2")

    def test_tenant_access_control_not_allowed(self):
        """Test tenant cannot access when not in allowed_tenants list."""
        registry = AgentRegistry(allowed_tenants=["tenant1", "tenant2"])

        with pytest.raises(PermissionError, match="not authorized"):
            registry._check_tenant_access("tenant3")

    def test_tenant_access_control_empty_allowed(self):
        """Test tenant access with empty allowed_tenants."""
        # When allowed_tenants is empty, the check should pass (for registry-level access)
        # The tenant-level access check is done elsewhere
        registry = AgentRegistry(allowed_tenants=[])

        # Should not raise - empty allowed_tenants means no restriction at registry level
        registry._check_tenant_access("tenant1")

    def test_tenant_access_control_register(self):
        """Test registering agent with tenant access control."""
        registry = AgentRegistry(allowed_tenants=["tenant1", "tenant2"])

        config = AgentConfig(
            agent_id="test",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )

        # Should work for allowed tenant
        registry.register("test", config, tenant_id="tenant1")
        assert registry.has_agent("test", tenant_id="tenant1")

        # Should fail for non-allowed tenant
        with pytest.raises(PermissionError, match="not authorized"):
            registry.register("test2", config, tenant_id="tenant3")

    def test_tenant_access_control_get(self):
        """Test getting agent with tenant access control."""
        registry = AgentRegistry(allowed_tenants=["tenant1", "tenant2"])

        config = AgentConfig(
            agent_id="test",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        registry.register("test", config)

        # Should work for allowed tenant
        result = registry.get("test", tenant_id="tenant1")
        assert result is not None
        assert result.agent_id == "test"

        # Should fail for non-allowed tenant
        with pytest.raises(PermissionError, match="not authorized"):
            registry.get("test", tenant_id="tenant3")
