"""LangGraph compatibility router for OpenClaw Gateway Service.

Provides endpoints compatible with LangGraph API for deep-agents-ui integration.
Mapping:
- Thread → Session
- Run → Chat message
- History → Session messages
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deps import TenantAwareGatewayClient

router = APIRouter()


# ===== Request/Response Models =====


class ThreadCreateRequest(BaseModel):
    """Request to create a new thread."""

    metadata: dict | None = None


class ThreadCreateResponse(BaseModel):
    """Response for thread creation."""

    thread_id: str
    metadata: dict | None = None


class RunCreateRequest(BaseModel):
    """Request to create a run (send a message)."""

    input: str
    stream: bool = False
    agent_id: str | None = None


class RunCreateResponse(BaseModel):
    """Response for run creation."""

    run_id: str
    thread_id: str
    output: str
    metadata: dict | None = None


class Message(BaseModel):
    """A message in thread history."""

    role: str  # "user" or "assistant"
    content: str


class HistoryResponse(BaseModel):
    """Response for thread history."""

    thread_id: str
    messages: list[Message]


# ===== Endpoints =====


@router.get("/ok")
async def health_check() -> dict:
    """Health check endpoint for LangGraph compatibility."""
    return {"status": "ok"}


@router.post("/threads", response_model=ThreadCreateResponse)
async def create_thread(
    request: ThreadCreateRequest,
    client: TenantAwareGatewayClient,
) -> ThreadCreateResponse:
    """Create a new thread (session).

    For LangGraph compatibility, we generate a thread ID but defer session creation
    until the first run is posted. The thread ID can be used as session ID.
    """
    thread_id = str(uuid.uuid4())
    # Note: Session will be created automatically when first chat is sent.
    return ThreadCreateResponse(
        thread_id=thread_id,
        metadata=request.metadata,
    )


@router.post("/threads/{thread_id}/runs", response_model=RunCreateResponse)
async def create_run(
    thread_id: str,
    request: RunCreateRequest,
    client: TenantAwareGatewayClient,
) -> RunCreateResponse:
    """Create a run (send a message) in a thread.

    Maps to GatewayClient.chat() with session_id = thread_id.
    """
    try:
        response = await client.chat(
            message=request.input,
            session_id=thread_id,
            agent_id=request.agent_id,
            stream=request.stream,
        )
        # Generate a run ID (for simplicity, use a UUID)
        run_id = str(uuid.uuid4())
        return RunCreateResponse(
            run_id=run_id,
            thread_id=thread_id,
            output=response.content,
            metadata=response.metadata,
        )
    except Exception as e:
        # Map specific exceptions to appropriate HTTP status codes
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/threads/{thread_id}/history", response_model=HistoryResponse)
async def get_thread_history(
    thread_id: str,
    client: TenantAwareGatewayClient,
) -> HistoryResponse:
    """Get thread history (session messages).

    Currently returns empty list as message storage is not implemented.
    TODO: Integrate with session message store.
    """
    # For now, return empty history.
    # In the future, we can retrieve messages from session metadata or a message store.
    return HistoryResponse(
        thread_id=thread_id,
        messages=[],
    )
