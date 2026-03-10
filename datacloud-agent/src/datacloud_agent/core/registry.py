"""Agent registry for OpenClaw Gateway.

Provides AgentConfig dataclass and AgentRegistry class for managing agent configurations.

Example:
    >>> from datacloud_agent.core import AgentRegistry, AgentConfig
    >>> registry = AgentRegistry()
    >>> config = AgentConfig(
    ...     agent_id="default",
    ...     provider="anthropic",
    ...     model="claude-sonnet-4-6",
    ...     system_prompt="You are a helpful assistant.",
    ...     tools=["know", "query"],
    ...     subagents=[]
    ... )
    >>> registry.register("default", config)
    >>> agents = registry.list_agents()
    >>> len(agents)
    1
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .subagents import get_default_subagents
from .tools import get_business_tools, get_system_prompt


# Tenant ID validation regex: 3-64 chars, lowercase letters, numbers, underscores, hyphens only
TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_-]{3,64}$")


@dataclass
class AgentConfig:
    """Configuration for an agent (deepagents version).

    Attributes:
        agent_id: Unique identifier for the agent.
        provider: Model provider (e.g., "anthropic", "openai").
        model: LLM model identifier (e.g., "claude-sonnet-4-6").
        system_prompt: Optional system prompt for the agent.
        tools: List of tool identifiers available to the agent.
        subagents: List of sub-agent configurations.
    """

    agent_id: str
    provider: str
    model: str
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=list)
    subagents: list[dict[str, Any]] = field(default_factory=list)


class AgentRegistry:
    """Registry for agent configurations.

    Supports loading from YAML files, registration, and agent creation.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        allowed_tenants: list[str] | None = None,
    ) -> None:
        """Initialize the registry.

        Args:
            config_path: Optional path to a YAML config file to load.
            allowed_tenants: List of tenant IDs that can access this registry.
        """
        self._agents: dict[str, AgentConfig] = {}
        self._allowed_tenants: list[str] = allowed_tenants or []
        if config_path is not None:
            self.load_from_yaml(config_path)

    def _validate_tenant_id(self, tenant_id: str) -> None:
        """Validate tenant ID format.

        Args:
            tenant_id: Tenant identifier to validate.

        Raises:
            ValueError: If tenant_id is invalid format.
        """
        if not TENANT_ID_PATTERN.match(tenant_id):
            raise ValueError(
                f"Invalid tenant_id '{tenant_id}': must be 3-64 characters, "
                "lowercase letters, numbers, underscores, or hyphens only"
            )

    def _check_tenant_access(self, tenant_id: str) -> None:
        """Check if tenant has access to the registry.

        Args:
            tenant_id: Tenant identifier to check.

        Raises:
            ValueError: If tenant_id format is invalid.
            PermissionError: If tenant is not authorized.
        """
        self._validate_tenant_id(tenant_id)

        # If allowed_tenants is empty, only allow access from tenant with same name as agent
        # (This is handled at agent level, not registry level)
        if self._allowed_tenants and tenant_id not in self._allowed_tenants:
            raise PermissionError(
                f"Tenant '{tenant_id}' is not authorized to access this registry. "
                f"Allowed tenants: {self._allowed_tenants}"
            )

    def load_from_yaml(self, path: Path) -> None:
        """Load agent configs from YAML file.

        Expected YAML format:
            agents:
                default:
                    provider: "anthropic"
                    model: "claude-sonnet-4-6"
                    system_prompt: "You are a helpful assistant."
                    tools: ["know", "query"]
                    subagents: []

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
            required = ["provider", "model"]
            missing = [field for field in required if field not in config]
            if missing:
                raise ValueError(f"Missing required fields for agent '{agent_id}': {missing}")

            agent_config = AgentConfig(
                agent_id=agent_id,
                provider=config["provider"],
                model=config["model"],
                system_prompt=config.get("system_prompt"),
                tools=config.get("tools", []),
                subagents=config.get("subagents", []),
            )
            if agent_id in new_agents:
                raise ValueError(f"Duplicate agent ID '{agent_id}' in YAML")
            new_agents[agent_id] = agent_config

        # Replace existing agents with the new ones
        self._agents.clear()
        self._agents.update(new_agents)

    def register(
        self,
        agent_id: str,
        config: AgentConfig,
        tenant_id: str | None = None,
    ) -> None:
        """Register an agent configuration.

        Args:
            agent_id: Unique identifier for the agent.
            config: AgentConfig instance.
            tenant_id: Optional tenant ID for access control.

        Raises:
            ValueError: If agent_id already registered or tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' already registered")
        self._agents[agent_id] = config

    def unregister(
        self,
        agent_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Unregister an agent configuration.

        Args:
            agent_id: Agent identifier.
            tenant_id: Optional tenant ID for access control.

        Returns:
            True if agent was removed, False if not found.

        Raises:
            ValueError: If tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def get(
        self,
        agent_id: str,
        tenant_id: str | None = None,
    ) -> AgentConfig | None:
        """Get agent configuration.

        Args:
            agent_id: Agent identifier.
            tenant_id: Optional tenant ID for access control.

        Returns:
            AgentConfig if found, None otherwise.

        Raises:
            ValueError: If tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        return self._agents.get(agent_id)

    def list_agents(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List all registered agents.

        Args:
            tenant_id: Optional tenant ID for access control.

        Returns:
            List of dictionaries with id, provider, model.

        Raises:
            ValueError: If tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        return [
            {"id": agent_id, "provider": config.provider, "model": config.model}
            for agent_id, config in self._agents.items()
        ]

    def create_agent(
        self,
        agent_id: str,
        model_override: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an agent instance using deepagents (mock for now).

        Args:
            agent_id: Agent identifier.
            model_override: Optional model to override the configured model.
            tenant_id: Optional tenant ID for access control.

        Returns:
            A mock agent object (placeholder).

        Raises:
            KeyError: If agent_id not found.
            ValueError: If tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        config = self.get(agent_id)
        if config is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        # For now, return a mock agent
        # In the future, this will call deepagents.create_deep_agent
        model = model_override if model_override is not None else config.model
        return {
            "agent_id": agent_id,
            "model": model,
            "provider": config.provider,
            "system_prompt": config.system_prompt,
            "tools": config.tools,
            "subagents": config.subagents,
        }

    def create_default_agent(
        self,
        agent_id: str,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        tenant_id: str | None = None,
    ) -> AgentConfig:
        """Create a default agent with default subagents and tools.

        Args:
            agent_id: Unique identifier for the agent.
            provider: Model provider (default: "anthropic").
            model: LLM model identifier (default: "claude-sonnet-4-20250514").
            tenant_id: Optional tenant ID for access control.

        Returns:
            Created AgentConfig instance.

        Raises:
            ValueError: If tenant_id invalid or agent already registered.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._validate_tenant_id(tenant_id)

        # Get default tools (list of tool names)
        business_tools = get_business_tools()
        tool_names = [tool.name for tool in business_tools]

        # Get default subagents
        default_subagents = get_default_subagents()

        # Get default system prompt
        default_system_prompt = get_system_prompt()

        config = AgentConfig(
            agent_id=agent_id,
            provider=provider,
            model=model,
            system_prompt=default_system_prompt,
            tools=tool_names,
            subagents=default_subagents,
        )

        self.register(agent_id, config, tenant_id=tenant_id)
        return config

    def has_agent(self, agent_id: str, tenant_id: str | None = None) -> bool:
        """Check if agent is registered.

        Args:
            agent_id: Agent identifier.
            tenant_id: Optional tenant ID for access control.

        Returns:
            True if agent exists.

        Raises:
            ValueError: If tenant_id invalid.
            PermissionError: If tenant is not authorized.
        """
        if tenant_id is not None:
            self._check_tenant_access(tenant_id)

        return agent_id in self._agents
