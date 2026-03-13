"""WebSocket support for OpenClaw Gateway Service.

Provides real-time bidirectional communication using OpenClaw Gateway protocol.
"""

import contextlib
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError

from datacloud_agent import GatewayClient
from datacloud_agent.config.models import GatewayConfig

from config import settings
from openclaw_protocol import OpenClawProtocolHandler

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
    tenant_id: Optional[str] = None,
) -> GatewayClient:
    """Get GatewayClient for WebSocket connection."""
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
    """WebSocket endpoint for OpenClaw protocol.

    Handles OpenClaw Gateway protocol frames for real-time chat.
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    # Get tenant ID from query or headers
    tenant_id = websocket.query_params.get("tenant_id") or websocket.headers.get("x-tenant-id")

    # Initialize client variable for cleanup
    client: GatewayClient | None = None

    try:
        # Create GatewayClient for this connection
        client = await get_websocket_gateway_client(websocket, tenant_id)

        # Create protocol handler
        handler = OpenClawProtocolHandler(client)

        # Main message loop
        while True:
            frame: dict = {}
            try:
                # Receive text message (JSON frame)
                data = await websocket.receive_text()
                frame = json.loads(data)

                # Handle the frame
                async def send_callback(response_frame: dict):
                    await websocket.send_text(json.dumps(response_frame))

                await handler.handle_frame(frame, send_callback)

            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON received: {e}")
                await websocket.send_text(
                    json.dumps({"type": "res", "ok": False, "error": "Invalid JSON"})
                )
            except Exception as e:
                logger.exception("Error handling WebSocket message")
                frame_id = frame.get("id") if frame else None
                await websocket.send_text(
                    json.dumps({"type": "res", "id": frame_id, "ok": False, "error": str(e)})
                )

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
        # Clean up all checkpointers when connection ends to prevent memory leak
        if client is not None and hasattr(client, "_agent_runner"):
            try:
                # Clear all checkpointers for this connection
                client._agent_runner._checkpointers.clear()
                logger.debug("Cleaned up all checkpointers for connection")
            except Exception:
                logger.exception("Error cleaning up checkpointers")
    except Exception:
        logger.exception("Unexpected error in WebSocket handler")
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
