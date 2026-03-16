"""Tests for AgentRegistry."""

from pathlib import Path
import pytest
import yaml

from datacloud_analysis.core import AgentConfig, AgentRegistry


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_agent_config_creation(self):
        """Test creating an AgentConfig with required fields."""
        config = AgentConfig(
            agent_id="test",
            model="claude-sonnet-4-6",
            provider="anthropic",
        )
        assert config.agent_id == "test"
        assert config.model == "claude-sonnet-4-6"
        assert config.provider == "anthropic"
        assert config.system_prompt is None
        assert config.tools == []
        assert config.subagents == []

    def test_agent_config_with_optional_fields(self):
        """Test AgentConfig with optional fields."""
        config = AgentConfig(
            agent_id="test",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="You are a test agent.",
            tools=["know", "query"],
            subagents=[{"agent_id": "sub1", "model": "model1", "provider": "provider1"}],
        )
        assert config.system_prompt == "You are a test agent."
        assert config.tools == ["know", "query"]
        assert config.subagents == [
            {"agent_id": "sub1", "model": "model1", "provider": "provider1"}
        ]

    def test_agent_config_defaults_are_independent(self):
        """Ensure default lists/dicts are independent instances."""
        config1 = AgentConfig(
            agent_id="test1",
            model="model1",
            provider="provider1",
        )
        config2 = AgentConfig(
            agent_id="test2",
            model="model2",
            provider="provider2",
        )
        config1.tools.append("know")
        config1.subagents.append({"agent_id": "sub1"})
        assert config2.tools == []
        assert config2.subagents == []


class TestAgentRegistryBasics:
    """Basic tests for AgentRegistry."""

    def test_init_empty(self):
        """Test initializing an empty registry."""
        registry = AgentRegistry()
        assert registry.list_agents() == []

    def test_register_and_get(self):
        """Test registering and retrieving an agent."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="claude-sonnet-4-6",
            provider="anthropic",
        )
        registry.register("default", config)
        retrieved = registry.get("default")
        assert retrieved is not None
        assert retrieved.agent_id == "default"
        assert retrieved.model == "claude-sonnet-4-6"
        assert retrieved.provider == "anthropic"

    def test_register_duplicate_raises(self):
        """Test that registering duplicate agent_id raises ValueError."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="model",
            provider="provider",
        )
        registry.register("default", config)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("default", config)

    def test_unregister_existing(self):
        """Test unregistering an existing agent."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="model",
            provider="provider",
        )
        registry.register("default", config)
        assert registry.unregister("default") is True
        assert registry.get("default") is None
        assert registry.list_agents() == []

    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent agent returns False."""
        registry = AgentRegistry()
        assert registry.unregister("nonexistent") is False

    def test_list_agents(self):
        """Test listing agents returns correct structure."""
        registry = AgentRegistry()
        config1 = AgentConfig(
            agent_id="agent1",
            model="model1",
            provider="provider1",
        )
        config2 = AgentConfig(
            agent_id="agent2",
            model="model2",
            provider="provider2",
        )
        registry.register("agent1", config1)
        registry.register("agent2", config2)

        agents = registry.list_agents()
        assert len(agents) == 2
        # Order may not be guaranteed, but we can check both
        agent_ids = {a["id"] for a in agents}
        assert agent_ids == {"agent1", "agent2"}

    def test_has_agent(self):
        """Test has_agent method."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="model",
            provider="provider",
        )
        registry.register("default", config)
        assert registry.has_agent("default") is True
        assert registry.has_agent("nonexistent") is False


class TestAgentRegistryYamlLoading:
    """Tests for YAML loading functionality."""

    def test_load_from_yaml_valid(self, tmp_path: Path):
        """Test loading from a valid YAML file."""
        yaml_content = """
        agents:
          default:
            model: "claude-sonnet-4-6"
            provider: "anthropic"
            system_prompt: "You are a helpful assistant."
            tools: ["know", "query"]
            subagents: []
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_file)
        config = registry.get("default")
        assert config is not None
        assert config.agent_id == "default"
        assert config.model == "claude-sonnet-4-6"
        assert config.provider == "anthropic"
        assert config.system_prompt == "You are a helpful assistant."
        assert config.tools == ["know", "query"]
        assert config.subagents == []

    def test_load_from_yaml_minimal(self, tmp_path: Path):
        """Test loading YAML with only required fields."""
        yaml_content = """
        agents:
          minimal:
            model: "gpt-4"
            provider: "openai"
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_file)
        config = registry.get("minimal")
        assert config is not None
        assert config.agent_id == "minimal"
        assert config.model == "gpt-4"
        assert config.provider == "openai"
        assert config.system_prompt is None
        assert config.tools == []
        assert config.subagents == []

    def test_load_from_yaml_multiple_agents(self, tmp_path: Path):
        """Test loading multiple agents from YAML."""
        yaml_content = """
        agents:
          agent1:
            model: "model1"
            provider: "provider1"
          agent2:
            model: "model2"
            provider: "provider2"
            tools: ["compute"]
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_file)
        assert len(registry.list_agents()) == 2
        assert registry.has_agent("agent1")
        assert registry.has_agent("agent2")

    def test_load_from_yaml_file_not_found(self):
        """Test loading from non-existent file raises FileNotFoundError."""
        registry = AgentRegistry()
        with pytest.raises(FileNotFoundError):
            registry.load_from_yaml(Path("/nonexistent/file.yaml"))

    def test_load_from_yaml_invalid_yaml(self, tmp_path: Path):
        """Test loading invalid YAML raises yaml.YAMLError."""
        config_file = tmp_path / "agents.yaml"
        config_file.write_text("invalid: [")

        registry = AgentRegistry()
        with pytest.raises(yaml.YAMLError):
            registry.load_from_yaml(config_file)

    def test_load_from_yaml_root_not_dict(self, tmp_path: Path):
        """Test YAML root not being a dictionary raises ValueError."""
        config_file = tmp_path / "agents.yaml"
        config_file.write_text("- item1\n- item2")

        registry = AgentRegistry()
        with pytest.raises(ValueError, match="root must be a dictionary"):
            registry.load_from_yaml(config_file)

    def test_load_from_yaml_agents_not_dict(self, tmp_path: Path):
        """Test 'agents' key not being a dictionary raises ValueError."""
        yaml_content = """
        agents: ["agent1", "agent2"]
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry()
        with pytest.raises(ValueError, match="'agents' must be a dictionary"):
            registry.load_from_yaml(config_file)

    def test_load_from_yaml_agent_config_not_dict(self, tmp_path: Path):
        """Test individual agent config not being a dictionary raises ValueError."""
        yaml_content = """
        agents:
          default: "just a string"
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry()
        with pytest.raises(ValueError, match="must be a dictionary"):
            registry.load_from_yaml(config_file)

    def test_load_from_yaml_missing_required_field(self, tmp_path: Path):
        """Test missing required field raises ValueError."""
        yaml_content = """
        agents:
          default:
            model: "claude-sonnet-4-6"
            # missing provider
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry()
        with pytest.raises(ValueError, match="Missing required fields"):
            registry.load_from_yaml(config_file)

    def test_load_from_yaml_extra_fields_go_to_subagents(self, tmp_path: Path):
        """Test that extra fields in YAML are handled properly."""
        yaml_content = """
        agents:
          default:
            model: "model"
            provider: "provider"
            extra_field: "should be ignored"
            subagents:
              - agent_id: "sub1"
                model: "submodel1"
                provider: "subprovider1"
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_file)
        config = registry.get("default")
        assert config is not None
        assert config.subagents == [
            {"agent_id": "sub1", "model": "submodel1", "provider": "subprovider1"}
        ]


class TestAgentRegistryCreateAgent:
    """Tests for create_agent method."""

    def test_create_agent_mock(self):
        """Test create_agent returns a mock agent with correct fields."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="claude-sonnet-4-6",
            provider="anthropic",
            system_prompt="Be helpful",
            tools=["know", "query"],
            subagents=[],
        )
        registry.register("default", config)

        agent = registry.create_agent("default")
        assert isinstance(agent, dict)
        assert agent["agent_id"] == "default"
        assert agent["model"] == "claude-sonnet-4-6"
        assert agent["provider"] == "anthropic"
        assert agent["system_prompt"] == "Be helpful"
        assert agent["tools"] == ["know", "query"]

    def test_create_agent_with_model_override(self):
        """Test create_agent with model override."""
        registry = AgentRegistry()
        config = AgentConfig(
            agent_id="default",
            model="claude-sonnet-4-6",
            provider="anthropic",
        )
        registry.register("default", config)

        agent = registry.create_agent("default", model_override="gpt-4")
        assert agent["model"] == "gpt-4"
        assert agent["provider"] == "anthropic"  # provider unchanged

    def test_create_agent_nonexistent_raises(self):
        """Test creating non-existent agent raises KeyError."""
        registry = AgentRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.create_agent("nonexistent")


class TestAgentRegistryIntegration:
    """Integration tests for AgentRegistry."""

    def test_init_with_config_path(self, tmp_path: Path):
        """Test initializing registry with config path."""
        yaml_content = """
        agents:
          default:
            model: "model"
            provider: "provider"
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_path=config_file)
        assert registry.has_agent("default")
        assert registry.list_agents()[0]["id"] == "default"

    def test_register_after_load(self, tmp_path: Path):
        """Test registering additional agents after loading from YAML."""
        yaml_content = """
        agents:
          from_yaml:
            model: "model1"
            provider: "provider1"
        """
        config_file = tmp_path / "agents.yaml"
        config_file.write_text(yaml_content)

        registry = AgentRegistry(config_file)
        config = AgentConfig(
            agent_id="manual",
            model="model2",
            provider="provider2",
        )
        registry.register("manual", config)

        assert len(registry.list_agents()) == 2
        assert registry.has_agent("from_yaml")
        assert registry.has_agent("manual")

    def test_load_from_yaml_twice_overwrites(self, tmp_path: Path):
        """Loading from YAML twice should overwrite existing agents."""
        yaml_content1 = """
        agents:
          agent1:
            name: "Agent One"
            description: "First"
            model: "model1"
            provider: "provider1"
        """
        config_file1 = tmp_path / "agents1.yaml"
        config_file1.write_text(yaml_content1)

        registry = AgentRegistry(config_file1)
        assert len(registry.list_agents()) == 1

        yaml_content2 = """
        agents:
          agent2:
            name: "Agent Two"
            description: "Second"
            model: "model2"
            provider: "provider2"
        """
        config_file2 = tmp_path / "agents2.yaml"
        config_file2.write_text(yaml_content2)

        registry.load_from_yaml(config_file2)
        # Should have only agent2, not agent1
        assert len(registry.list_agents()) == 1
        assert registry.has_agent("agent2")
        assert not registry.has_agent("agent1")
