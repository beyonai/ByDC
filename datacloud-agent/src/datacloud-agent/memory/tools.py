"""MCP memory tools given to the Agent (design §4.3.2.2 Track-2).

Three-layer progressive search workflow
---------------------------------------
Layer 1  ``search_memory``  — broad index search; returns id + title list only
                              (token-efficient; model uses this to find the ID).
Layer 2  ``read_memory``    — precise detail fetch by ID; returns full content.
Layer 3  inject & apply     — model incorporates the retrieved memory into its
                              reasoning (no extra tool call required).

``recall_memory`` is a convenience wrapper for the ``recall_memory`` tool
referenced in the 3.1 tool list (maps to the search → read workflow).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_memory(query: str, user_id: str, limit: int = 5) -> list[dict[str, str]]:
    """Layer-1: search the user's long-term memory index.

    Returns a compact list of ``{id, title}`` dicts so the model can find
    the right entry ID without fetching large content blocks.

    Args:
        query:    Natural-language search query.
        user_id:  The current user (memory is per-user).
        limit:    Maximum number of results.
    """
    try:
        from datacloud_memory.query import search_experiences  # noqa: PLC0415

        items = await search_experiences(user_id=user_id, query=query, limit=limit)
        return [{"id": item["id"], "title": item["title"]} for item in items]
    except ImportError:
        logger.debug("datacloud-memory not available; returning empty search results.")
        return []


@tool
async def read_memory(memory_id: str, user_id: str) -> str:
    """Layer-2: retrieve the full content of a specific memory entry by ID.

    Args:
        memory_id: The ID returned by ``search_memory``.
        user_id:   The current user.
    """
    try:
        from datacloud_memory.query import get_experience_by_id  # noqa: PLC0415

        item = await get_experience_by_id(user_id=user_id, memory_id=memory_id)
        return item.get("content", "") if item else ""
    except ImportError:
        logger.debug("datacloud-memory not available; returning empty content.")
        return ""


@tool
async def recall_memory(query: str, user_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """Convenience: search memory and return id + title + short snippet.

    Used when the model wants a quick recall without a dedicated read step.

    Args:
        query:   What to look for.
        user_id: The current user.
        limit:   Maximum results.
    """
    try:
        from datacloud_memory.query import search_experiences  # noqa: PLC0415

        return await search_experiences(user_id=user_id, query=query, limit=limit)
    except ImportError:
        logger.debug("datacloud-memory not available; returning empty recall.")
        return []
