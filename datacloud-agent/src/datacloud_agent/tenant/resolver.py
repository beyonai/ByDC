"""Tenant resolver for extracting tenant context from various sources."""

import re
from dataclasses import dataclass

from datacloud_agent.tenant.context import TenantContext
from datacloud_agent.tenant.types import TenantType


@dataclass
class TenantResolver:
    """Resolver for extracting tenant information from different sources."""

    def resolve_from_path(self, path: str) -> TenantContext:
        """Extract tenant from file path.

        Expected path format:
        - user_private/{tenant_id}/...
        - user_public/{tenant_id}/...
        - public/...

        Args:
            path: File path to extract tenant from.

        Returns:
            TenantContext extracted from the path.

        Raises:
            ValueError: If path format is invalid.
        """
        # Remove leading/trailing slashes and split
        parts = path.strip("/").split("/")

        if len(parts) < 1:
            raise ValueError(f"Invalid path format: {path}")

        tenant_type_str = parts[0]

        try:
            tenant_type = TenantType(tenant_type_str)
        except ValueError as err:
            raise ValueError(f"Unknown tenant type: {tenant_type_str}") from err

        if tenant_type == TenantType.PUBLIC:
            return TenantContext(
                tenant_id="public",
                tenant_type=tenant_type,
            )
        elif len(parts) < 2:
            raise ValueError(f"Missing tenant_id in path: {path}")

        tenant_id = parts[1]
        return TenantContext(
            tenant_id=tenant_id,
            tenant_type=tenant_type,
        )

    def resolve_from_session(self, session_key: str) -> TenantContext:
        """Extract tenant from session key.

        Expected session key format:
        - user_private_{tenant_id}_{session_id}
        - user_public_{tenant_id}_{session_id}
        - public_{session_id}

        Args:
            session_key: Session key to extract tenant from.

        Returns:
            TenantContext extracted from the session key.
        """
        # Pattern: tenant_type_tenantId_sessionId
        pattern = r"^(user_private|user_public|public)_(.+)$"
        match = re.match(pattern, session_key)

        if not match:
            # Default to public if no pattern match
            return TenantContext(
                tenant_id="public",
                tenant_type=TenantType.PUBLIC,
                session_id=session_key,
            )

        tenant_type_str = match.group(1)
        rest = match.group(2)

        try:
            tenant_type = TenantType(tenant_type_str)
        except ValueError:
            return TenantContext(
                tenant_id="public",
                tenant_type=TenantType.PUBLIC,
                session_id=session_key,
            )

        if tenant_type == TenantType.PUBLIC:
            return TenantContext(
                tenant_id="public",
                tenant_type=tenant_type,
                session_id=rest,
            )

        # For user_private/user_public, format is tenantId_sessionId
        parts = rest.split("_", 1)
        tenant_id = parts[0]
        session_id = parts[1] if len(parts) > 1 else None

        return TenantContext(
            tenant_id=tenant_id,
            tenant_type=tenant_type,
            session_id=session_id,
        )
