"""Types for Gateway API."""

from dataclasses import dataclass, field
from typing import Any

# Re-export config types for API convenience
from datacloud_agent.config.models import (
    AgentConfig,
    GatewayConfig,
    InboundConfig,
    MessagesConfig,
    QueueConfig,
)
from datacloud_agent.queue.types import QueueMode

__all__ = [
    "ChatResponse",
    "ChatChunk",
    "GatewayConfig",
    "MessagesConfig",
    "InboundConfig",
    "QueueConfig",
    "AgentConfig",
    "QueueMode",
]


@dataclass
class ChatResponse:
    """Response from a chat request.

    Attributes:
        content: The response content.
        session_id: The session ID.
        agent_id: The agent ID that generated the response.
        metadata: Additional metadata about the response.
    """

    content: str
    session_id: str
    agent_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatChunk:
    """A single chunk from a streaming chat response.

    Attributes:
        content: The chunk content.
        is_last: Whether this is the last chunk.
        metadata: Additional metadata about the chunk.
    """

    content: str
    is_last: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
