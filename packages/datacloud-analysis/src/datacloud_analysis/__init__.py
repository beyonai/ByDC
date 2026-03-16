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

from . import bootstrap
from .agent import create_agent

__all__ = ["bootstrap", "create_agent"]
