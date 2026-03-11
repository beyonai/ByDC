"""Gateway API module.

Provides GatewayClient, types, and exceptions for OpenClaw Gateway communication.
"""

from datacloud_agent.api.client import GatewayClient
from datacloud_agent.api.exceptions import (
    AgentNotFoundError,
    GatewayConnectionError,
    GatewayError,
    GatewayTimeoutError,
    SessionNotFoundError,
)
from datacloud_agent.api.types import ChatChunk, ChatResponse

__all__ = [
    # Client
    "GatewayClient",
    # Types
    "ChatResponse",
    "ChatChunk",
    # Exceptions
    "GatewayError",
    "GatewayTimeoutError",
    "GatewayConnectionError",
    "SessionNotFoundError",
    "AgentNotFoundError",
]
