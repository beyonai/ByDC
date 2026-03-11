"""datacloud-agent - DataCloud agent for Deep Agents UI.

Provides a LangGraph-compatible deep agent using the configured LLM,
to be served via langgraph dev and used with ui/deep-agents-ui.
"""

from .agent import create_agent

__all__ = ["create_agent"]
