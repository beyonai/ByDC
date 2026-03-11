"""OpenClaw WebSocket Protocol Handler.

Implements the OpenClaw Gateway protocol for WebSocket communication.
This allows the OpenClaw UI to communicate with the gateway service.
"""

import asyncio
import logging
import os
import uuid

from datacloud_agent import GatewayClient
from datacloud_agent.core import AgentConfig

from config import settings

logger = logging.getLogger(__name__)

# Check if we have API key for real LLM calls (check env var directly)
_HAS_API_KEY = bool(os.getenv("OPENAI_API_KEY") or settings.openai_api_key)


def ensure_default_agent(client: GatewayClient) -> None:
    """Ensure a default agent is registered in the client.

    Args:
        client: The GatewayClient instance to configure.
    """
    registry = client._agent_registry

    # Check if default agent already exists
    if registry.get("default") is not None:
        return

    # Create and register a default agent
    try:
        config = AgentConfig(
            agent_id="default",
            provider="openai",
            model="qwen3.5-plus",
            system_prompt="You are a helpful AI assistant for DataCloud. You help users with data analysis, queries, and general questions.",
            tools=["know", "query"],
            subagents=[],
        )
        registry.register("default", config)
        logger.info("Registered default agent")
    except ValueError as e:
        # Agent might already exist
        logger.debug(f"Default agent registration skipped: {e}")


class OpenClawProtocolHandler:
    """Handler for OpenClaw WebSocket protocol frames."""

    def __init__(self, gateway_client: GatewayClient):
        self.client = gateway_client
        self.active_streams = {}  # session_id -> stream_task

        # Ensure default agent is registered
        ensure_default_agent(self.client)

    async def handle_frame(self, frame: dict, send_callback) -> None:
        """Handle an incoming protocol frame.

        Args:
            frame: The parsed JSON frame
            send_callback: Async function to send response frames
        """
        frame_type = frame.get("type")
        frame_id = frame.get("id")
        method = frame.get("method")
        params = frame.get("params", {})

        if frame_type != "req":
            logger.warning(f"Unexpected frame type: {frame_type}")
            return

        try:
            # Route to appropriate handler
            method_name = method.replace(".", "_") if method else ""
            handler = getattr(self, f"handle_{method_name}", None) if method else None
            if handler:
                result = await handler(params, send_callback, frame_id)
                await send_callback({"type": "res", "id": frame_id, "ok": True, "payload": result})
            else:
                await send_callback(
                    {
                        "type": "res",
                        "id": frame_id,
                        "ok": False,
                        "error": f"Unknown method: {method}",
                    }
                )
        except Exception as e:
            logger.exception(f"Error handling method {method}")
            await send_callback({"type": "res", "id": frame_id, "ok": False, "error": str(e)})

    async def handle_sessions_list(self, params: dict, send_callback, frame_id: str) -> list:
        """List all chat sessions."""
        # Return empty list - sessions are managed per-connection
        return []

    async def handle_sessions_create(self, params: dict, send_callback, frame_id: str) -> dict:
        """Create a new chat session."""
        import time

        session_id = str(uuid.uuid4())
        return {
            "id": session_id,
            "title": params.get("title", "New Chat"),
            "createdAt": int(time.time() * 1000),
            "updatedAt": int(time.time() * 1000),
        }

    async def handle_chat_history(self, params: dict, send_callback, frame_id: str) -> list:
        """Get chat history for a session."""
        # Return empty list - messages are stored client-side
        return []

    async def handle_chat_send(self, params: dict, send_callback, frame_id: str) -> dict:
        """Send a chat message and stream the response."""
        session_id = params.get("sessionId")
        message = params.get("message")

        if not message:
            raise ValueError("Message is required")

        # Use mock response if no API key is configured
        effective_session_id = session_id or str(uuid.uuid4())
        if not _HAS_API_KEY:
            asyncio.create_task(
                self._mock_stream_response(effective_session_id, message, send_callback)
            )
        else:
            # Start streaming response using real LLM
            asyncio.create_task(
                self._real_stream_response(effective_session_id, message, send_callback)
            )

        return {"sessionId": effective_session_id, "status": "streaming"}

    async def _mock_stream_response(self, session_id: str, message: str, send_callback) -> None:
        """Send a mock response when no API key is available."""
        try:
            # Simulate typing delay
            await asyncio.sleep(0.5)

            # Send mock response chunks
            mock_response = (
                f"**你好！** 我是 OpenClaw Agent。\n\n"
                f'你发送的消息是："{message}"\n\n'
                f"> **注意**：当前后端运行在模拟模式下，因为没有配置 LLM API key。\n\n"
                f"要启用真实 AI 响应，请设置以下环境变量：\n"
                f"- `OPENAI_API_KEY` - 用于 OpenAI 兼容的 API\n"
                f"- `OPENAI_BASE_URL` - API 基础 URL（可选）\n\n"
                f"前后端连接已成功建立！"
            )

            # Stream response in chunks
            chunk_size = 10
            for i in range(0, len(mock_response), chunk_size):
                chunk = mock_response[i : i + chunk_size]
                is_last = i + chunk_size >= len(mock_response)

                await send_callback(
                    {
                        "type": "event",
                        "event": "chat.chunk",
                        "payload": {
                            "sessionId": session_id,
                            "content": chunk,
                            "isLast": is_last,
                        },
                    }
                )
                await asyncio.sleep(0.05)  # Small delay between chunks

            # Send completion event
            await send_callback(
                {
                    "type": "event",
                    "event": "chat.complete",
                    "payload": {"sessionId": session_id},
                }
            )
        except Exception as e:
            logger.exception("Error in mock streaming")
            await send_callback(
                {
                    "type": "event",
                    "event": "chat.error",
                    "payload": {"sessionId": session_id, "message": str(e)},
                }
            )

    async def _real_stream_response(self, session_id: str, message: str, send_callback) -> None:
        """Send a real LLM response."""
        try:
            logger.info(f"Starting real stream response for session {session_id}")

            # Use chat method to get full response
            response = await self.client.chat(
                message=message, session_id=session_id, agent_id="default", stream=False
            )

            logger.info(f"Got response: {response.content[:50]}...")

            # Stream response in chunks to simulate streaming
            content = response.content
            chunk_size = 20
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]
                is_last = i + chunk_size >= len(content)

                await send_callback(
                    {
                        "type": "event",
                        "event": "chat.chunk",
                        "payload": {
                            "sessionId": session_id,
                            "content": chunk,
                            "isLast": is_last,
                        },
                    }
                )
                await asyncio.sleep(0.03)  # Small delay between chunks

            # Send completion event
            await send_callback(
                {
                    "type": "event",
                    "event": "chat.complete",
                    "payload": {"sessionId": session_id},
                }
            )
        except Exception as e:
            logger.exception("Error streaming response")
            await send_callback(
                {
                    "type": "event",
                    "event": "chat.error",
                    "payload": {"sessionId": session_id, "message": str(e)},
                }
            )

    async def handle_chat_abort(self, params: dict, send_callback, frame_id: str) -> dict:
        """Abort an ongoing chat stream."""
        session_id = params.get("sessionId")
        # Implementation depends on how we track active streams
        return {"sessionId": session_id, "status": "aborted"}

    async def handle_health(self, params: dict, send_callback, frame_id: str) -> dict:
        """Health check."""
        return {"status": "healthy", "service": settings.service_name}
