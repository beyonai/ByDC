"""Agent registry for OpenClaw Gateway.

Provides AgentConfig dataclass and AgentRegistry class for managing agent configurations.

Example:
    >>> from datacloud_agent.core import AgentRegistry, AgentConfig
    >>> registry = AgentRegistry()
    >>> config = AgentConfig(
    ...     agent_id="default",
    ...     name="Default Agent",
    ...     description="General purpose agent",
    ...     model="claude-sonnet-4-6",
    ...     provider="anthropic"
    ... )
    >>> registry.register("default", config)
    >>> agents = registry.list_agents()
    >>> len(agents)
    1
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentConfig:
    """Configuration for an agent.

    Attributes:
        agent_id: Unique identifier for the agent.
        name: Human-readable name.
        description: Description of the agent's purpose.
        model: LLM model identifier (e.g., "claude-sonnet-4-6").
        provider: Model provider (e.g., "anthropic").
        system_prompt: Optional system prompt for the agent.
        tools: List of tool identifiers available to the agent.
        metadata: Additional configuration metadata.
    """

    agent_id: str
    name: str
    description: str
    model: str
    provider: str
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """Registry for agent configurations.

    Supports loading from YAML files, registration, and agent creation.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the registry.

        Args:
            config_path: Optional path to a YAML config file to load.
        """
        self._agents: dict[str, AgentConfig] = {}
        if config_path is not None:
            self.load_from_yaml(config_path)

    def load_from_yaml(self, path: Path) -> None:
        """Load agent configs from YAML file.

        Expected YAML format:
            agents:
                default:
                    name: "Default Agent"
                    description: "General purpose agent"
                    model: "claude-sonnet-4-6"
                    provider: "anthropic"
                    system_prompt: "You are a helpful assistant."
                    tools: ["know", "query"]

        Args:
            path: Path to YAML file.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the YAML is malformed.
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("YAML root must be a dictionary")

        agents = data.get("agents", {})
        if not isinstance(agents, dict):
            raise ValueError("'agents' must be a dictionary")

        new_agents: dict[str, AgentConfig] = {}
        for agent_id, config in agents.items():
            if not isinstance(config, dict):
                raise ValueError(f"Agent config for '{agent_id}' must be a dictionary")

            # Ensure required fields are present
            required = ["name", "description", "model", "provider"]
            missing = [field for field in required if field not in config]
            if missing:
                raise ValueError(f"Missing required fields for agent '{agent_id}': {missing}")

            agent_config = AgentConfig(
                agent_id=agent_id,
                name=config["name"],
                description=config["description"],
                model=config["model"],
                provider=config["provider"],
                system_prompt=config.get("system_prompt"),
                tools=config.get("tools", []),
                metadata=config.get("metadata", {}),
            )
            if agent_id in new_agents:
                raise ValueError(f"Duplicate agent ID '{agent_id}' in YAML")
            new_agents[agent_id] = agent_config

        # Replace existing agents with the new ones
        self._agents.clear()
        self._agents.update(new_agents)

    def register(self, agent_id: str, config: AgentConfig) -> None:
        """Register an agent configuration.

        Args:
            agent_id: Unique identifier for the agent.
            config: AgentConfig instance.

        Raises:
            ValueError: If agent_id already registered.
        """
        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' already registered")
        self._agents[agent_id] = config

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent configuration.

        Args:
            agent_id: Agent identifier.

        Returns:
            True if agent was removed, False if not found.
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def get(self, agent_id: str) -> AgentConfig | None:
        """Get agent configuration.

        Args:
            agent_id: Agent identifier.

        Returns:
            AgentConfig if found, None otherwise.
        """
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents.

        Returns:
            List of dictionaries with id, name, description.
        """
        return [
            {"id": agent_id, "name": config.name, "description": config.description}
            for agent_id, config in self._agents.items()
        ]

    def create_agent(self, agent_id: str, model_override: str | None = None) -> dict[str, Any]:
        """Create an agent instance using deepagents (mock for now).

        Args:
            agent_id: Agent identifier.
            model_override: Optional model to override the configured model.

        Returns:
            A mock agent object (placeholder).

        Raises:
            KeyError: If agent_id not found.
        """
        config = self.get(agent_id)
        if config is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        # For now, return a mock agent
        # In the future, this will call deepagents.create_deep_agent
        model = model_override if model_override is not None else config.model
        return {
            "agent_id": agent_id,
            "name": config.name,
            "model": model,
            "provider": config.provider,
            "system_prompt": config.system_prompt,
            "tools": config.tools,
            "metadata": config.metadata,
        }

    def has_agent(self, agent_id: str) -> bool:
        """Check if agent is registered.

        Args:
            agent_id: Agent identifier.

        Returns:
            True if agent exists.
        """
        return agent_id in self._agents
