"""WebSocket support for OpenClaw Gateway Service.

Provides real-time bidirectional communication for chat, commands, and events.
"""

import contextlib
import json
import logging

from datacloud_agent import GatewayClient
from datacloud_agent.config.models import GatewayConfig
from fastapi import WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError

from config import settings

logger = logging.getLogger(__name__)


class WebSocketMessage(BaseModel):
    """Base WebSocket message model."""

    type: str
    session_id: str | None = None
    message: str | None = None
    agent_id: str | None = None
    command: str | None = None


async def get_websocket_gateway_client(
    websocket: WebSocket,
    tenant_id: str | None = None,
) -> GatewayClient:
    """Get GatewayClient for WebSocket connection.

    Extracts tenant ID from query parameters or headers.
    """
    # Try to get tenant ID from query parameter
    if not tenant_id:
        tenant_id = websocket.query_params.get("tenant_id")

    # Try to get from headers
    if not tenant_id:
        tenant_id = websocket.headers.get("x-tenant-id")

    # Parse host and port from gateway_api_url
    api_url = settings.gateway_api_url
    if "://" in api_url:
        api_url = api_url.split("://", 1)[1]
    if ":" in api_url:
        host_part, port_part = api_url.rsplit(":", 1)
        try:
            port = int(port_part)
        except ValueError:
            port = 8080
    else:
        host_part = api_url
        port = 8080

    config = GatewayConfig(
        host=host_part,
        port=port,
        debug=settings.reload,
        log_level=settings.log_level,
    )

    client = GatewayClient(config=config, tenant_id=tenant_id)
    return client


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication.

    Handles:
    - Connection establishment
    - Message parsing and validation
    - Chat message streaming
    - Command execution
    - Ping/pong keepalive
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    # Get tenant ID from query or headers
    tenant_id = websocket.query_params.get("tenant_id") or websocket.headers.get("x-tenant-id")

    try:
        # Create GatewayClient for this connection
        client = await get_websocket_gateway_client(websocket, tenant_id)

        # Main message loop
        while True:
            try:
                # Receive JSON message
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON message"})
                continue

            # Validate message
            try:
                msg = WebSocketMessage(**data)
            except ValidationError as e:
                await websocket.send_json(
                    {"type": "error", "error": f"Invalid message format: {e.errors()}"}
                )
                continue

            # Route message by type
            if msg.type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg.type == "chat":
                if not msg.message:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing 'message' for chat type"}
                    )
                    continue

                # Stream chat response
                try:
                    async for chunk in client.chat_stream(
                        message=msg.message,
                        session_id=msg.session_id,
                        agent_id=msg.agent_id,
                    ):
                        await websocket.send_json(
                            {
                                "type": "chat_chunk",
                                "content": chunk.content,
                                "is_last": chunk.is_last,
                            }
                        )
                except Exception as e:
                    logger.exception("Error during chat streaming")
                    await websocket.send_json({"type": "error", "error": f"Chat error: {str(e)}"})

            elif msg.type == "command":
                if not msg.command:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing 'command' for command type"}
                    )
                    continue

                try:
                    result = await client.execute_command(
                        command=msg.command,
                        session_id=msg.session_id,
                    )
                    await websocket.send_json(
                        {
                            "type": "command_result",
                            "result": result,
                        }
                    )
                except Exception as e:
                    logger.exception("Error executing command")
                    await websocket.send_json(
                        {"type": "error", "error": f"Command error: {str(e)}"}
                    )

            else:
                await websocket.send_json(
                    {"type": "error", "error": f"Unknown message type: {msg.type}"}
                )

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception:
        logger.exception("Unexpected error in WebSocket handler")
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
