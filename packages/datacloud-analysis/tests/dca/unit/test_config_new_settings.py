"""Tests for new Settings classes added in P2."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestAgentSettings:
    def test_default_locale(self) -> None:
        from datacloud_analysis.config.env import AgentSettings

        with patch.dict(os.environ, {}, clear=False):
            # Unset the env var to test default
            env = {k: v for k, v in os.environ.items() if k != "DATACLOUD_AGENT_LOCALE"}
            with patch.dict(os.environ, env, clear=True):
                settings = AgentSettings()
        assert settings.locale == "zh_CN"

    def test_locale_from_env(self) -> None:
        from datacloud_analysis.config.env import AgentSettings

        with patch.dict(os.environ, {"DATACLOUD_AGENT_LOCALE": "en_US"}):
            settings = AgentSettings()
        assert settings.locale == "en_US"


class TestGatewaySettings:
    def test_default_values(self) -> None:
        from datacloud_analysis.config.env import GatewaySettings

        env = {k: v for k, v in os.environ.items() if not k.startswith("DATACLOUD_GATEWAY_")}
        with patch.dict(os.environ, env, clear=True):
            settings = GatewaySettings()

        assert settings.redis_host == ""
        assert settings.redis_port == 6379
        assert settings.redis_username == ""
        assert settings.redis_password == ""
        assert settings.redis_db == 0
        assert settings.worker_id == ""

    def test_values_from_env(self) -> None:
        from datacloud_analysis.config.env import GatewaySettings

        with patch.dict(
            os.environ,
            {
                "DATACLOUD_GATEWAY_REDIS_HOST": "redis.local",
                "DATACLOUD_GATEWAY_REDIS_PORT": "6380",
                "DATACLOUD_GATEWAY_WORKER_ID": "worker-1",
            },
        ):
            settings = GatewaySettings()

        assert settings.redis_host == "redis.local"
        assert settings.redis_port == 6380
        assert settings.worker_id == "worker-1"


class TestAIFactorySettings:
    def test_agent_ids_json_array(self) -> None:
        from datacloud_analysis.config.env import AIFactorySettings

        with patch.dict(
            os.environ,
            {
                "DATACLOUD_AI_FACTORY_TOKEN": "tok123",
                "DATACLOUD_AI_FACTORY_AGENT_IDS": '["agent-1", "agent-2"]',
            },
        ):
            settings = AIFactorySettings()

        assert settings.token == "tok123"
        assert settings.agent_ids == ["agent-1", "agent-2"]

    def test_agent_ids_empty_string(self) -> None:
        from datacloud_analysis.config.env import AIFactorySettings

        env = {k: v for k, v in os.environ.items() if not k.startswith("DATACLOUD_AI_FACTORY_")}
        with patch.dict(os.environ, env, clear=True):
            settings = AIFactorySettings()

        assert settings.agent_ids == []

    def test_agent_ids_single_string_fallback(self) -> None:
        """A single JSON string (not array) should become a single-item list."""
        from datacloud_analysis.config.env import AIFactorySettings

        with patch.dict(
            os.environ,
            {
                "DATACLOUD_AI_FACTORY_AGENT_IDS": '["agent-a"]',
            },
        ):
            settings = AIFactorySettings()

        assert settings.agent_ids == ["agent-a"]


class TestExecutionSettings:
    def test_default_react_max_rounds(self) -> None:
        from datacloud_analysis.config.env import ExecutionSettings

        env = {k: v for k, v in os.environ.items() if k != "DATACLOUD_REACT_MAX_ROUNDS"}
        with patch.dict(os.environ, env, clear=True):
            settings = ExecutionSettings()

        assert settings.react_max_rounds == 10

    def test_react_max_rounds_from_env(self) -> None:
        from datacloud_analysis.config.env import ExecutionSettings

        with patch.dict(os.environ, {"DATACLOUD_REACT_MAX_ROUNDS": "20"}):
            settings = ExecutionSettings()

        assert settings.react_max_rounds == 20
