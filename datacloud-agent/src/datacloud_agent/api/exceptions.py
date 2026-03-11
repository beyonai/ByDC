"""Exceptions for Gateway API."""


class GatewayError(Exception):
    """Base exception for Gateway errors."""

    pass


class GatewayTimeoutError(GatewayError):
    """Raised when a gateway operation times out."""

    pass


class GatewayConnectionError(GatewayError):
    """Raised when a connection error occurs."""

    pass


class SessionNotFoundError(GatewayError):
    """Raised when a session is not found."""

    pass


class AgentNotFoundError(GatewayError):
    """Raised when an agent is not found."""

    pass
