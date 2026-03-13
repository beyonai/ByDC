"""T_KNOW_SEARCH — enterprise knowledge & terminology search (design §3.1).

Calls the ``datacloud-knowledge-service`` to retrieve relevant domain
knowledge (ontology, term definitions, business rules) before the Agent
starts planning.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_knowledge(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search the enterprise knowledge base for relevant context.

    Args:
        query: Natural-language search query.
        top_k: Maximum number of knowledge snippets to return.

    Returns:
        List of ``{title, content, source}`` dicts.
    """
    try:
        from datacloud_knowledge_service.client import search  # noqa: PLC0415

        return await search(query=query, top_k=top_k)
    except ImportError:
        logger.warning("datacloud-knowledge-service not available; returning empty results.")
        return []
