"""FastAPI application factory and main entry point.

Creates and configures the FastAPI application with:
- Lifespan management for startup/shutdown
- CORS middleware
- Health check endpoint
- API routes (to be added in T17)
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from lifespan import lifespan

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This factory function creates a new FastAPI instance with:
    - Lifespan context manager for startup/shutdown
    - CORS middleware
    - Health check endpoint
    - Placeholder for API routes

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.service_name,
        description="DataCloud Agent Service - FastAPI Gateway Service Layer",
        version=settings.service_version,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Health status dictionary
        """
        return {
            "status": "healthy",
            "service": settings.service_name,
            "version": settings.service_version,
        }

    # API routes (T17)
    from routers import agents_router, chat_router, sessions_router

    app.include_router(chat_router, prefix="/v1", tags=["chat"])
    app.include_router(sessions_router, prefix="/v1", tags=["sessions"])
    app.include_router(agents_router, prefix="/v1", tags=["agents"])

    # LangGraph compatibility routes (T19)
    from routers import langgraph

    app.include_router(langgraph.router, tags=["langgraph"])

    # WebSocket endpoint
    from websocket import websocket_endpoint

    app.websocket("/ws")(websocket_endpoint)

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers,
    )
