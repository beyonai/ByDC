"""DataCloud deep agent for use with Deep Agents UI.

Uses the same LLM config as content_writer (Qwen via whale lab proxy)
and exposes a minimal deep agent compatible with langgraph dev.
"""

from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

# Default model config (align with content_writer 167-172)
DEFAULT_MODEL = "openai:Qwen/Qwen3-235B-A22B"
DEFAULT_API_KEY = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
DEFAULT_BASE_URL = "https://lab.iwhalecloud.com/gpt-proxy/v1"
DEFAULT_TEMPERATURE = 0.7


def create_agent(
    *,
    model: str = DEFAULT_MODEL,
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = DEFAULT_TEMPERATURE,
    system_prompt: str | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui.

    Args:
        model: Model identifier (e.g. openai:Qwen/...).
        api_key: API key for the LLM endpoint.
        base_url: Base URL for the API.
        temperature: Sampling temperature.
        system_prompt: Optional system prompt; default describes a DataCloud assistant.

    Returns:
        A LangGraph-compilable deep agent.
    """
    llm = init_chat_model(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )

    if system_prompt is None:
        system_prompt = (
            "You are a helpful DataCloud assistant. You help users with analysis, "
            "questions, and tasks. Be concise and accurate."
        )

    return create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
    )
