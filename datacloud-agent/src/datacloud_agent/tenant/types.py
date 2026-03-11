"""Tenant types for multi-tenant support."""

from enum import Enum


class TenantType(Enum):
    """Tenant type enumeration."""

    USER_PRIVATE = "user_private"
    USER_PUBLIC = "user_public"
    PUBLIC = "public"
