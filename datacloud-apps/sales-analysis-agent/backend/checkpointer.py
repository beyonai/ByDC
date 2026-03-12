"""langgraph dev checkpointer entry point for sales-analysis-agent.

The OpenGauss-compatible implementation lives in the core engine:
    datacloud_agent.session.pg_opengauss

langgraph.json references this file as:
    "checkpointer": {"backend": "custom", "path": "./checkpointer.py:get_checkpointer"}
"""

from datacloud_agent.session.pg_opengauss import get_checkpointer  # noqa: F401

__all__ = ["get_checkpointer"]
