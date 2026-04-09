"""datacloud-analysis — 超级分析智能体 SDK.

Quick-start::

    import asyncio
    from datacloud_analysis import bootstrap
    from datacloud_analysis.agent import create_agent

    async def main():
        await bootstrap.setup()   # one-time SDK init (PG tables, env validation)
        agent = create_agent()
        ...

    asyncio.run(main())
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import bootstrap


def create_agent(*args: Any, **kwargs: Any) -> Any:
    """Lazily import agent factory to avoid import-time graph side effects."""
    from .agent import create_agent as _create_agent

    factory: Callable[..., Any] = _create_agent
    return factory(*args, **kwargs)


__all__ = ["bootstrap", "create_agent"]
