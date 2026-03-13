"""Unit tests for model_config module."""

import os
from unittest.mock import patch

import pytest

from datacloud_agent.core.model_config import create_model, get_default_model_config


class TestGetDefaultModelConfig:
    """Tests for get_default_model_config function."""

    def test_returns_dict_with_model_key(self):
        """Test that the function returns a dictionary with 'model' key."""
        config = get_default_model_config()
        assert isinstance(config, dict)
        assert "model" in config

    def test_default_model_is_qwen(self):
        """Test that the default model is qwen3.5-plus."""
        config = get_default_model_config()
        assert config["model"] == "openai:qwen3.5-plus"

    def test_includes_api_key_from_env(self):
        """Test that api_key is included in the config."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            config = get_default_model_config()
            assert "api_key" in config

    def test_includes_base_url_from_env(self):
        """Test that base_url is included in the config."""
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://test.url"}):
            config = get_default_model_config()
            assert "base_url" in config


class TestCreateModel:
    """Tests for create_model function."""

    def test_raises_error_when_no_api_key(self):
        """Test that ValueError is raised when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key is required"):
                create_model({})

    def test_raises_error_when_api_key_empty(self):
        """Test that ValueError is raised when API key is empty string."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with pytest.raises(ValueError, match="API key is required"):
                create_model({})

    def test_uses_api_key_from_config(self):
        """Test that API key from config is used when provided."""
        with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
            mock_model.return_value = "mock_model"
            result = create_model({"api_key": "test-key-123"})
            assert result == "mock_model"
            mock_model.assert_called_once()
            call_kwargs = mock_model.call_args[1]
            assert call_kwargs["api_key"] == "test-key-123"

    def test_uses_api_key_from_env_when_not_in_config(self):
        """Test that API key from environment is used when not in config."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key-456"}):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({})
                mock_model.assert_called_once()
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["api_key"] == "env-key-456"

    def test_uses_base_url_from_config(self):
        """Test that base_url from config is used when provided."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({"base_url": "https://custom.url/v1"})
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["base_url"] == "https://custom.url/v1"

    def test_uses_base_url_from_env_when_not_in_config(self):
        """Test that base_url from environment is used when not in config."""
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_BASE_URL": "https://env.url/v1"}
        ):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({})
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["base_url"] == "https://env.url/v1"

    def test_uses_default_model_when_not_specified(self):
        """Test that default model is used when not specified."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({})
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["model"] == "openai:qwen3.5-plus"

    def test_uses_custom_model_from_config(self):
        """Test that custom model from config is used when specified."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({"model": "openai:gpt-4"})
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["model"] == "openai:gpt-4"

    def test_passes_none_base_url_when_not_set(self):
        """Test that base_url is None when not provided anywhere."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model({})
                call_kwargs = mock_model.call_args[1]
                assert call_kwargs["base_url"] is None

    def test_config_none_uses_env_defaults(self):
        """Test that config=None uses environment variable defaults."""
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_BASE_URL": "https://env.url"}
        ):
            with patch("datacloud_agent.core.model_config.ChatOpenAI") as mock_model:
                mock_model.return_value = "mock_model"
                result = create_model(None)
                assert result == "mock_model"
