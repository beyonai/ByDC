"""OpenClaw WebSocket Protocol Handler.

Implements the OpenClaw Gateway protocol for WebSocket communication.
This allows the OpenClaw UI to communicate with datacloud-agent-service.
"""

import json
import logging
import uuid
from typing import Any

from datacloud_agent import GatewayClient

logger = logging.getLogger(__name__)


class OpenClawProtocolHandler:
    """Handler for OpenClaw WebSocket protocol frames."""

    def __init__(self, gateway_client: GatewayClient):
        self.client = gateway_client
        self.active_streams = {}  # session_id -> stream_task

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
            handler = getattr(self, f"handle_{method.replace('.', '_')}", None)
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
        # For now, return empty list or implement session storage
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
        # Return empty list - messages are stored client-side for now
        return []

    async def handle_chat_send(self, params: dict, send_callback, frame_id: str) -> dict:
        """Send a chat message and stream the response."""
        session_id = params.get("sessionId")
        message = params.get("message")

        if not message:
            raise ValueError("Message is required")

        # Start streaming response
        async def stream_response():
            try:
                async for chunk in self.client.chat_stream(
                    message=message, session_id=session_id, agent_id="default"
                ):
                    await send_callback(
                        {
                            "type": "event",
                            "event": "chat.chunk",
                            "payload": {
                                "sessionId": session_id,
                                "content": chunk.content,
                                "isLast": chunk.is_last,
                            },
                        }
                    )

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

        # Start streaming in background
        import asyncio

        asyncio.create_task(stream_response())

        return {"sessionId": session_id, "status": "streaming"}

    async def handle_chat_abort(self, params: dict, send_callback, frame_id: str) -> dict:
        """Abort an ongoing chat stream."""
        session_id = params.get("sessionId")
        # Implementation depends on how we track active streams
        return {"sessionId": session_id, "status": "aborted"}

    async def handle_health(self, params: dict, send_callback, frame_id: str) -> dict:
        """Health check."""
        return {"status": "healthy", "service": "datacloud-agent-service"}
