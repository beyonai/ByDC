"""Configuration loader utilities for OpenClaw Gateway."""

from pathlib import Path
from typing import Any

import yaml

from datacloud_agent.config.models import GatewayConfig


def load_config_from_dict(data: dict[str, Any]) -> GatewayConfig:
    """Load configuration from a dictionary.

    Args:
        data: Dictionary containing configuration values.

    Returns:
        GatewayConfig instance.
    """
    return GatewayConfig(**data)


def load_config_from_yaml(yaml_str: str) -> GatewayConfig:
    """Load configuration from a YAML string.

    Args:
        yaml_str: YAML string containing configuration values.

    Returns:
        GatewayConfig instance.
    """
    data = yaml.safe_load(yaml_str)
    return load_config_from_dict(data)


def load_config_from_file(path: Path) -> GatewayConfig:
    """Load configuration from a YAML or JSON file.

    Args:
        path: Path to the configuration file.

    Returns:
        GatewayConfig instance.

    Raises:
        ValueError: If the file format is not supported.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif suffix == ".json":
        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    return load_config_from_dict(data)
