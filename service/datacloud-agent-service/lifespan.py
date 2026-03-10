"""Service lifespan lifecycle management.

Handles startup and shutdown events for the FastAPI application.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: "FastAPI") -> AsyncGenerator[None, None]:
    """Manage application lifespan.

    This context manager handles startup and shutdown events:
    - Startup: Initialize GatewayClient, logging, health checks
    - Shutdown: Cleanup resources, close connections

    Args:
        app: The FastAPI application instance

    Yields:
        None during the application lifecycle
    """
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"Gateway API URL: {settings.gateway_api_url}")
    logger.info(f"Server config: {settings.host}:{settings.port}")

    # TODO: Initialize GatewayClient connection pool
    # TODO: Setup monitoring/health checks
    # TODO: Warm up agent registry

    logger.info("Service startup complete")

    yield

    # Shutdown
    logger.info("Shutting down service...")

    # TODO: Close GatewayClient connections
    # TODO: Flush pending operations
    # TODO: Cleanup resources

    logger.info("Service shutdown complete")


# Forward reference for type hint
from fastapi import FastAPI  # noqa: E402
