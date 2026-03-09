"""Session management routes.

Provides endpoints for creating, retrieving, and deleting agent sessions.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deps import TenantAwareGatewayClient

router = APIRouter()


class SessionCreateRequest(BaseModel):
    """Request to create a new session."""

    agent_id: str = Field(
        default="default",
        description="The agent ID to associate with the session",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for the session",
    )


class SessionResponse(BaseModel):
    """Session response model."""

    session_id: str = Field(..., description="Unique session identifier")
    session_key: str = Field(..., description="Full session key")
    tenant_id: str = Field(..., description="Tenant identifier")
    agent_id: str = Field(..., description="Agent identifier")
    created_at: datetime = Field(..., description="Timestamp when session was created")
    updated_at: datetime = Field(..., description="Timestamp when session was last updated")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional extra data")


class SessionsListResponse(BaseModel):
    """Response containing a list of sessions."""

    sessions: list[SessionResponse] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    gateway_client: TenantAwareGatewayClient,
) -> SessionResponse:
    """Create a new session.

    Args:
        request: Session creation request
        gateway_client: Gateway client instance

    Returns:
        The created session

    Raises:
        HTTPException: If session creation fails
    """
    try:
        # Access the internal session manager to create a session
        # Note: This uses a private API; in a real implementation, GatewayClient
        # should expose a public create_session method.
        session = await gateway_client._session_manager.create_session(
            tenant_ctx=gateway_client._tenant_ctx,
            agent_id=request.agent_id,
            metadata=request.metadata or {},
        )
        return SessionResponse(
            session_id=session.session_id,
            session_key=session.session_key,
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=session.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    gateway_client: TenantAwareGatewayClient,
) -> SessionResponse:
    """Get session information.

    Args:
        session_id: The session ID
        gateway_client: Gateway client instance

    Returns:
        The session information

    Raises:
        HTTPException: If session is not found
    """
    # We need to find the session across all agents for this tenant
    sessions = await gateway_client._session_manager.list_sessions(
        tenant_id=gateway_client.tenant_id
    )
    target_session = None
    for session in sessions:
        if session.session_id == session_id:
            target_session = session
            break

    if not target_session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=target_session.session_id,
        session_key=target_session.session_key,
        tenant_id=target_session.tenant_id,
        agent_id=target_session.agent_id,
        created_at=target_session.created_at,
        updated_at=target_session.updated_at,
        metadata=target_session.metadata,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    gateway_client: TenantAwareGatewayClient,
) -> dict[str, Any]:
    """Delete a session.

    Args:
        session_id: The session ID
        gateway_client: Gateway client instance

    Returns:
        Success message

    Raises:
        HTTPException: If session is not found
    """
    # Find the session across all agents for this tenant
    sessions = await gateway_client._session_manager.list_sessions(
        tenant_id=gateway_client.tenant_id
    )
    target_session = None
    for session in sessions:
        if session.session_id == session_id:
            target_session = session
            break

    if not target_session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete the session
    await gateway_client._session_manager.delete_session(target_session.session_key)

    return {"message": "Session deleted successfully"}


@router.get("/sessions", response_model=SessionsListResponse)
async def list_sessions(
    gateway_client: TenantAwareGatewayClient,
) -> SessionsListResponse:
    """List all sessions for the current tenant.

    Args:
        gateway_client: Gateway client instance

    Returns:
        List of sessions
    """
    sessions = await gateway_client._session_manager.list_sessions(
        tenant_id=gateway_client.tenant_id
    )
    return SessionsListResponse(
        sessions=[
            SessionResponse(
                session_id=session.session_id,
                session_key=session.session_key,
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                metadata=session.metadata,
            )
            for session in sessions
        ],
        total=len(sessions),
    )
