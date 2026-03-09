"""FastAPI dependency injection providers.

Provides reusable dependencies for route handlers including
GatewayClient instances, configuration, and request context.
"""

from typing import Annotated

from datacloud_agent import GatewayClient
from datacloud_agent.config.models import GatewayConfig
from fastapi import Depends, Header, HTTPException, Request

from config import settings


async def get_gateway_client(request: Request) -> GatewayClient:
    """Get or create a GatewayClient for the current request.

    The GatewayClient is created per-request with tenant isolation
    based on the X-Tenant-ID header.

    Args:
        request: The FastAPI request object

    Returns:
        Configured GatewayClient instance

    Raises:
        HTTPException: If tenant ID is missing (when required)
    """
    # Extract tenant ID from request state (set by middleware)
    tenant_id = getattr(request.state, "tenant_id", None)

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

    # Create gateway config from service settings
    config = GatewayConfig(
        host=host_part,
        port=port,
        debug=settings.reload,
        log_level=settings.log_level,
    )

    # Create client with tenant context
    client = GatewayClient(
        config=config,
        tenant_id=tenant_id,
    )

    return client


async def get_tenant_id(x_tenant_id: Annotated[str | None, Header()] = None) -> str | None:
    """Extract tenant ID from request headers.

    Args:
        x_tenant_id: X-Tenant-ID header value

    Returns:
        Tenant ID if provided, None otherwise
    """
    return x_tenant_id


async def verify_tenant(tenant_id: Annotated[str | None, Depends(get_tenant_id)]) -> str:
    """Verify that tenant ID is provided (for protected endpoints).

    Args:
        tenant_id: Extracted tenant ID

    Returns:
        Valid tenant ID

    Raises:
        HTTPException: If tenant ID is missing
    """
    if not tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-ID header is required")
    return tenant_id


# Type aliases for commonly used dependencies
TenantAwareGatewayClient = Annotated[GatewayClient, Depends(get_gateway_client)]
VerifiedTenant = Annotated[str, Depends(verify_tenant)]
OptionalTenant = Annotated[str | None, Depends(get_tenant_id)]
