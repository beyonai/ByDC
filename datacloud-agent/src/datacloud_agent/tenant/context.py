"""Tenant context using contextvars for thread-safe isolation."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from datacloud_agent.tenant.types import TenantType


# Context variable for tenant isolation
tenant_ctx: ContextVar["TenantContext | None"] = ContextVar("tenant_ctx", default=None)


@dataclass
class TenantContext:
    """Tenant context for multi-tenant isolation.

    Attributes:
        tenant_id: Unique identifier for the tenant.
        tenant_type: Type of tenant (USER_PRIVATE, USER_PUBLIC, PUBLIC).
        session_id: Optional session identifier.
        task_id: Optional task identifier.
        metadata: Optional extra data for the context.
    """

    tenant_id: str
    tenant_type: TenantType
    session_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def scoped(self) -> Any:
        """Set this context as the current and return a token for resetting.

        Returns:
            Token that can be used to reset the context.
        """
        return tenant_ctx.set(self)

    @staticmethod
    def reset(token: Any) -> None:
        """Reset the context to its previous state using the token.

        Args:
            token: Token returned from scoped() call.
        """
        tenant_ctx.reset(token)

    @staticmethod
    def get_current() -> "TenantContext | None":
        """Get the current tenant context.

        Returns:
            Current TenantContext or None if not set.
        """
        return tenant_ctx.get()

    def get_path_prefix(self) -> str:
        """Get the path prefix based on tenant type.

        Returns:
            Path prefix string (e.g., 'user_private/user_001').
        """
        return f"{self.tenant_type.value}/{self.tenant_id}"


@contextmanager
def tenant_scope(tenant: TenantContext):
    """Context manager for tenant scope.

    Args:
        tenant: TenantContext to set for this scope.

    Yields:
        The TenantContext.
    """
    token = tenant.scoped()
    try:
        yield tenant
    finally:
        TenantContext.reset(token)
