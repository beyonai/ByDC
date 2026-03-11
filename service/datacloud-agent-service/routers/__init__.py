"""Router exports for the OpenClaw Gateway Service.

This module previously exported REST API routers, but OpenClaw now uses
WebSocket protocol exclusively. Kept for backward compatibility.
"""

# OpenClaw uses WebSocket protocol exclusively via /ws endpoint
# No REST routers needed

__all__ = []
