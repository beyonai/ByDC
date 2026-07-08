"""RPC-like unified router for datacloud-platform.

Usage in server.py::

    from datacloud_platform.api.routers.rpc import create_rpc_router
    app.include_router(create_rpc_router(platform))
"""

from __future__ import annotations

from datacloud_platform.api.routers.rpc.router import create_rpc_router

__all__ = ["create_rpc_router"]
