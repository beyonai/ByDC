"""Service lifespan lifecycle management.

Handles startup and shutdown events for the FastAPI application.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: "FastAPI") -> AsyncGenerator[None, None]:
    """Manage application lifespan.

    This context manager handles startup and shutdown events:
    - Startup: Initialize logging, verify configuration
    - Shutdown: Cleanup resources

    Args:
        app: The FastAPI application instance

    Yields:
        None during the application lifecycle
    """
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"Server config: {settings.host}:{settings.port}")

    # Check LLM configuration (check both env var and settings)
    api_key = os.getenv("OPENAI_API_KEY") or settings.openai_api_key
    if api_key:
        logger.info("LLM API: Configured (real mode)")
    else:
        logger.info("LLM API: Not configured (mock mode)")

    logger.info("Service startup complete")

    yield

    # Shutdown
    logger.info("Shutting down service...")
    logger.info("Service shutdown complete")


# Forward reference for type hint
from fastapi import FastAPI  # noqa: E402
