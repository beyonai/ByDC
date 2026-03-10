"""Agent management routes.

Provides endpoints for listing and retrieving agent configurations.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deps import TenantAwareGatewayClient

router = APIRouter()


class AgentResponse(BaseModel):
    """Agent configuration response."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Description of the agent's purpose")
    model: str = Field(..., description="LLM model identifier")
    provider: str = Field(..., description="Model provider")
    system_prompt: str | None = Field(
        default=None, description="Optional system prompt for the agent"
    )
    tools: list[str] = Field(default_factory=list, description="List of tool identifiers available")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional configuration metadata"
    )


class AgentsListResponse(BaseModel):
    """Response containing a list of agents."""

    agents: list[AgentResponse] = Field(..., description="List of agents")
    total: int = Field(..., description="Total number of agents")


@router.get("/agents", response_model=AgentsListResponse)
async def list_agents(gateway_client: TenantAwareGatewayClient) -> AgentsListResponse:
    """List all available agents.

    Args:
        gateway_client: Gateway client instance

    Returns:
        List of agent configurations
    """
    agents = gateway_client.list_agents()
    return AgentsListResponse(
        agents=[
            AgentResponse(
                agent_id=agent.get("agent_id", ""),
                name=agent.get("name", ""),
                description=agent.get("description", ""),
                model=agent.get("model", ""),
                provider=agent.get("provider", ""),
                system_prompt=agent.get("system_prompt"),
                tools=agent.get("tools", []),
                metadata=agent.get("metadata", {}),
            )
            for agent in agents
        ],
        total=len(agents),
    )


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, gateway_client: TenantAwareGatewayClient) -> AgentResponse:
    """Get agent details.

    Args:
        agent_id: The agent ID
        gateway_client: Gateway client instance

    Returns:
        Agent configuration

    Raises:
        HTTPException: If agent is not found
    """
    agents = gateway_client.list_agents()
    target_agent = None
    for agent in agents:
        if agent.get("agent_id") == agent_id:
            target_agent = agent
            break

    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentResponse(
        agent_id=target_agent.get("agent_id", ""),
        name=target_agent.get("name", ""),
        description=target_agent.get("description", ""),
        model=target_agent.get("model", ""),
        provider=target_agent.get("provider", ""),
        system_prompt=target_agent.get("system_prompt"),
        tools=target_agent.get("tools", []),
        metadata=target_agent.get("metadata", {}),
    )
