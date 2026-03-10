"""GatewayClient - High-level API for OpenClaw Gateway."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from datacloud_agent.api.exceptions import (
    AgentNotFoundError,
    SessionNotFoundError,
)
from datacloud_agent.api.types import ChatChunk, ChatResponse
from datacloud_agent.config.models import GatewayConfig
from datacloud_agent.core.registry import AgentRegistry
from datacloud_agent.core.router import CommandRouter
from datacloud_agent.core.runner import AgentRunner
from datacloud_agent.core.session import SessionManager
from datacloud_agent.events.emitter import EventEmitter
from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.types import QueueMode
from datacloud_agent.tenant.context import TenantContext
from datacloud_agent.tenant.types import TenantType

logger = logging.getLogger(__name__)


class GatewayClient:
    """High-level client for interacting with the OpenClaw Gateway.

    This is the main entry point for SDK users. It provides a simple API
    for chatting with agents, managing sessions, and executing commands.

    Example:
        ```python
        client = GatewayClient()
        response = await client.chat("Hello, world!")
        print(response.content)
        ```
    """

    def __init__(
        self,
        config: GatewayConfig | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Initialize the GatewayClient.

        Args:
            config: Optional gateway configuration. Uses defaults if not provided.
            tenant_id: Optional tenant ID for multi-tenant scenarios.
        """
        self.config = config or GatewayConfig()
        self.tenant_id = tenant_id or "default"

        # Initialize tenant context
        self._tenant_ctx = TenantContext(
            tenant_id=self.tenant_id,
            tenant_type=TenantType.USER_PRIVATE,
        )

        # Initialize core components
        self._event_emitter = EventEmitter()
        self._queue_manager = QueueManager()
        self._session_manager = SessionManager()
        self._agent_registry = AgentRegistry()
        self._command_router = CommandRouter()
        self._agent_runner = AgentRunner(
            config=self.config,
            session_manager=self._session_manager,
            agent_registry=self._agent_registry,
            event_emitter=self._event_emitter,
            queue_manager=self._queue_manager,
        )

        logger.debug("GatewayClient initialized for tenant: %s", self.tenant_id)

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        stream: bool = False,
    ) -> ChatResponse:
        """Send a message and get a response.

        Args:
            message: The message to send.
            session_id: Optional session ID. Creates new session if not provided.
            agent_id: Optional agent ID. Uses default agent if not provided.
            stream: Whether to stream the response. If True, use chat_stream instead.

        Returns:
            ChatResponse with the agent's response.

        Raises:
            SessionNotFoundError: If session_id is provided but not found.
            AgentNotFoundError: If agent_id is provided but not found.
            GatewayError: For other errors.
        """
        if stream:
            # Collect streamed chunks into a single response
            chunks = []
            async for chunk in self.chat_stream(message, session_id, agent_id):
                chunks.append(chunk.content)
            content = "".join(chunks)
            return ChatResponse(
                content=content,
                session_id=session_id or "",
                agent_id=agent_id or "default",
            )

        # Get or create session
        session = await self._get_or_create_session(session_id, agent_id)
        session_key = session.session_key

        # Handle the message through the agent runner
        result = await self._agent_runner.handle_message(
            session_key=session_key,
            prompt=message,
            queue_mode=QueueMode.COLLECT,
        )

        # Extract response content from result
        # Result structure: {'status': 'executed', 'session_key': '...', 'result': {'agent_id': '...', 'messages': [...], 'response': '...', 'usage': {...}}}
        content = ""
        if isinstance(result, dict):
            inner_result = result.get("result", {})
            if isinstance(inner_result, dict):
                content = inner_result.get("response", "")
            else:
                content = str(inner_result)
        else:
            content = str(result)

        return ChatResponse(
            content=content,
            session_id=session.session_id,
            agent_id=session.agent_id,
            metadata={"status": result.get("status", "unknown")}
            if isinstance(result, dict)
            else {},
        )

    async def chat_stream(
        self,
        message: str,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Send a message and stream the response.

        Args:
            message: The message to send.
            session_id: Optional session ID. Creates new session if not provided.
            agent_id: Optional agent ID. Uses default agent if not provided.

        Yields:
            ChatChunk objects containing response fragments.

        Raises:
            SessionNotFoundError: If session_id is provided but not found.
            AgentNotFoundError: If agent_id is provided but not found.
        """
        # Get or create session
        session = await self._get_or_create_session(session_id, agent_id)
        session_key = session.session_key

        # For now, simulate streaming by yielding the full response as one chunk
        # In a real implementation, this would integrate with event streaming
        result = await self._agent_runner.handle_message(
            session_key=session_key,
            prompt=message,
            queue_mode=QueueMode.COLLECT,
        )

        # Extract response content from result
        # Result structure: {'status': 'executed', 'session_key': '...', 'result': {'agent_id': '...', 'messages': [...], 'response': '...', 'usage': {...}}}
        content = ""
        if isinstance(result, dict):
            inner_result = result.get("result", {})
            if isinstance(inner_result, dict):
                content = inner_result.get("response", "")
            else:
                content = str(inner_result)
        else:
            content = str(result)

        yield ChatChunk(content=content, is_last=True)

    async def switch_agent(
        self,
        agent_id: str,
        session_id: str | None = None,
    ) -> None:
        """Switch the agent for a session.

        Args:
            agent_id: The ID of the agent to switch to.
            session_id: Optional session ID. Uses default session if not provided.

        Raises:
            AgentNotFoundError: If the agent is not found.
            SessionNotFoundError: If session_id is provided but not found.
        """
        # Verify agent exists
        if not self._agent_registry.get(agent_id):
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        # Get session
        if session_id:
            session = await self._session_manager.get_session(
                f"tenant:{self.tenant_id}:agent:{agent_id}:{session_id}"
            )
            if not session:
                raise SessionNotFoundError(f"Session '{session_id}' not found")
        else:
            # Create new session with the agent
            session = await self._session_manager.create_session(
                tenant_ctx=self._tenant_ctx,
                agent_id=agent_id,
            )

        # Update session agent
        session.agent_id = agent_id
        logger.debug("Switched session %s to agent %s", session.session_id, agent_id)

    async def reset_session(self, session_id: str | None = None) -> None:
        """Reset/clear a session.

        Args:
            session_id: Optional session ID. Resets default session if not provided.

        Raises:
            SessionNotFoundError: If session_id is provided but not found.
        """
        if session_id:
            # Find the session with any agent
            sessions = await self._session_manager.list_sessions(tenant_id=self.tenant_id)
            target_session = None
            for session in sessions:
                if session.session_id == session_id:
                    target_session = session
                    break

            if not target_session:
                raise SessionNotFoundError(f"Session '{session_id}' not found")

            await self._session_manager.reset_session(target_session.session_key)
        else:
            # Reset all sessions for this tenant
            sessions = await self._session_manager.list_sessions(tenant_id=self.tenant_id)
            for session in sessions:
                await self._session_manager.reset_session(session.session_key)

        logger.debug("Reset session(s) for tenant: %s", self.tenant_id)

    def list_agents(self) -> list[dict[str, Any]]:
        """List available agents.

        Returns:
            List of agent dictionaries with id, name, and other metadata.
        """
        agents = self._agent_registry.list_agents()
        return agents

    async def execute_command(
        self,
        command: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a slash command.

        Args:
            command: The command string (e.g., "/model coder").
            session_id: Optional session ID for context.

        Returns:
            Dictionary with command result.

        Raises:
            SessionNotFoundError: If session_id is provided but not found.
        """
        # Parse the command
        result = self._command_router.parse_command(command)

        if not result:
            return {
                "success": False,
                "error": "Invalid command format",
                "command": command,
            }

        # Handle specific commands
        if result.command == "model" and result.args:
            # Switch agent
            agent_id = result.args[0]
            try:
                await self.switch_agent(agent_id, session_id)
                return {
                    "success": True,
                    "command": "model",
                    "agent_id": agent_id,
                    "message": f"Switched to agent: {agent_id}",
                }
            except AgentNotFoundError as e:
                return {
                    "success": False,
                    "command": "model",
                    "error": str(e),
                }

        elif result.command == "reset":
            # Reset session
            try:
                await self.reset_session(session_id)
                return {
                    "success": True,
                    "command": "reset",
                    "message": "Session reset successfully",
                }
            except SessionNotFoundError as e:
                return {
                    "success": False,
                    "command": "reset",
                    "error": str(e),
                }

        elif result.command == "help":
            return {
                "success": True,
                "command": "help",
                "message": "Available commands: /model <agent>, /reset, /help",
            }

        return {
            "success": True,
            "command": result.command,
            "args": result.args,
        }

    async def _get_or_create_session(
        self,
        session_id: str | None,
        agent_id: str | None,
    ) -> Any:
        """Get existing session or create a new one.

        Args:
            session_id: Optional session ID.
            agent_id: Optional agent ID.

        Returns:
            Session object.
        """
        effective_agent_id = agent_id or "default"

        if session_id:
            # Try to get existing session
            session_key = f"tenant:{self.tenant_id}:agent:{effective_agent_id}:{session_id}"
            session = await self._session_manager.get_session(session_key)
            if session:
                return session

        # Create new session
        session = await self._session_manager.create_session(
            tenant_ctx=self._tenant_ctx,
            agent_id=effective_agent_id,
        )
        return session
