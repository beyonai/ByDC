"""Tests for OpenClaw Gateway configuration."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from datacloud_agent.config import (
    AgentConfig,
    GatewayConfig,
    InboundConfig,
    MessagesConfig,
    QueueConfig,
    load_config_from_dict,
    load_config_from_file,
    load_config_from_yaml,
)


class TestGatewayConfig:
    """Tests for GatewayConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = GatewayConfig()
        assert config.port == 8080
        assert config.host == "127.0.0.1"
        assert config.debug is False
        assert config.log_level == "INFO"

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = GatewayConfig(port=9090, host="0.0.0.0", debug=True, log_level="DEBUG")
        assert config.port == 9090
        assert config.host == "0.0.0.0"
        assert config.debug is True
        assert config.log_level == "DEBUG"

    def test_nested_configs(self):
        """Test nested configuration models."""
        config = GatewayConfig(
            messages=MessagesConfig(max_message_length=2048),
            inbound=InboundConfig(debounce_ms=200),
            queue=QueueConfig(max_queue_size=500),
            agent=AgentConfig(default_agent="test_agent"),
        )
        assert config.messages.max_message_length == 2048
        assert config.inbound.debounce_ms == 200
        assert config.queue.max_queue_size == 500
        assert config.agent.default_agent == "test_agent"

    def test_invalid_port(self):
        """Test validation error for invalid port."""
        with pytest.raises(ValidationError):
            GatewayConfig(port=0)
        with pytest.raises(ValidationError):
            GatewayConfig(port=70000)

    def test_invalid_log_level(self):
        """Test that invalid log level is accepted (no strict validation)."""
        config = GatewayConfig(log_level="INVALID")
        assert config.log_level == "INVALID"


class TestMessagesConfig:
    """Tests for MessagesConfig model."""

    def test_default_values(self):
        """Test default message configuration."""
        config = MessagesConfig()
        assert config.max_message_length == 1048576
        assert config.default_queue_mode == "async"

    def test_custom_values(self):
        """Test custom message configuration."""
        config = MessagesConfig(max_message_length=2048, default_queue_mode="sync")
        assert config.max_message_length == 2048
        assert config.default_queue_mode == "sync"


class TestInboundConfig:
    """Tests for InboundConfig model."""

    def test_default_values(self):
        """Test default inbound configuration."""
        config = InboundConfig()
        assert config.debounce_ms == 100
        assert config.dedupe_window_ms == 500

    def test_custom_values(self):
        """Test custom inbound configuration."""
        config = InboundConfig(debounce_ms=200, dedupe_window_ms=1000)
        assert config.debounce_ms == 200
        assert config.dedupe_window_ms == 1000


class TestQueueConfig:
    """Tests for QueueConfig model."""

    def test_default_values(self):
        """Test default queue configuration."""
        config = QueueConfig()
        assert config.default_mode == "async"
        assert config.max_queue_size == 1000
        assert config.drop_policy == "reject"

    def test_custom_values(self):
        """Test custom queue configuration."""
        config = QueueConfig(default_mode="sync", max_queue_size=500, drop_policy="drop_oldest")
        assert config.default_mode == "sync"
        assert config.max_queue_size == 500
        assert config.drop_policy == "drop_oldest"


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_default_values(self):
        """Test default agent configuration."""
        config = AgentConfig()
        assert config.default_agent == "main"
        assert config.available_agents == {}

    def test_custom_values(self):
        """Test custom agent configuration."""
        config = AgentConfig(
            default_agent="test",
            available_agents={"test": "test_type", "main": "main_type"},
        )
        assert config.default_agent == "test"
        assert config.available_agents == {"test": "test_type", "main": "main_type"}


class TestLoadConfigFromDict:
    """Tests for load_config_from_dict function."""

    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        data = {"port": 9000, "host": "localhost", "debug": True}
        config = load_config_from_dict(data)
        assert config.port == 9000
        assert config.host == "localhost"
        assert config.debug is True

    def test_load_from_dict_with_nested(self):
        """Test loading configuration with nested configs."""
        data = {
            "port": 9000,
            "messages": {"max_message_length": 4096},
            "agent": {"default_agent": "my_agent", "available_agents": {"my_agent": "custom"}},
        }
        config = load_config_from_dict(data)
        assert config.port == 9000
        assert config.messages.max_message_length == 4096
        assert config.agent.default_agent == "my_agent"
        assert config.agent.available_agents == {"my_agent": "custom"}


class TestLoadConfigFromYaml:
    """Tests for load_config_from_yaml function."""

    def test_load_from_yaml_string(self):
        """Test loading configuration from YAML string."""
        yaml_str = "port: 9090\nhost: 0.0.0.0\ndebug: true"
        config = load_config_from_yaml(yaml_str)
        assert config.port == 9090
        assert config.host == "0.0.0.0"
        assert config.debug is True

    def test_load_from_yaml_with_nested(self):
        """Test loading nested configuration from YAML."""
        yaml_str = """
port: 9000
messages:
  max_message_length: 2048
  default_queue_mode: sync
inbound:
  debounce_ms: 150
queue:
  max_queue_size: 500
  drop_policy: drop_newest
agent:
  default_agent: yaml_agent
"""
        config = load_config_from_yaml(yaml_str)
        assert config.port == 9000
        assert config.messages.max_message_length == 2048
        assert config.messages.default_queue_mode == "sync"
        assert config.inbound.debounce_ms == 150
        assert config.queue.max_queue_size == 500
        assert config.queue.drop_policy == "drop_newest"
        assert config.agent.default_agent == "yaml_agent"


class TestLoadConfigFromFile:
    """Tests for load_config_from_file function."""

    def test_load_from_yaml_file(self):
        """Test loading configuration from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("port: 9000\nhost: 0.0.0.0\ndebug: true\n")
            temp_path = Path(f.name)

        try:
            config = load_config_from_file(temp_path)
            assert config.port == 9000
            assert config.host == "0.0.0.0"
            assert config.debug is True
        finally:
            temp_path.unlink()

    def test_load_from_json_file(self):
        """Test loading configuration from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"port": 8000, "host": "localhost", "debug": False}, f)
            temp_path = Path(f.name)

        try:
            config = load_config_from_file(temp_path)
            assert config.port == 8000
            assert config.host == "localhost"
            assert config.debug is False
        finally:
            temp_path.unlink()

    def test_unsupported_file_format(self):
        """Test error for unsupported file format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("port: 9000\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                load_config_from_file(temp_path)
        finally:
            temp_path.unlink()
