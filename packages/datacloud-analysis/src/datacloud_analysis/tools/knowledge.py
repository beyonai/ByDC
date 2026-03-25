"""T_KNOW_SEARCH — enterprise knowledge & terminology search (design §3.1).

Calls the ``datacloud-knowledge-service`` to retrieve relevant domain
knowledge (ontology, term definitions, business rules) before the Agent
starts planning.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_knowledge(query: str, n_hops: int = 4) -> str:
    """Search the enterprise knowledge graph and return semantic tree text.

    Queries the knowledge graph to retrieve entities, relationships, and KPI definitions.
    Returns a tree-structured semantic text description.

    Args:
        query: Natural-language search query (e.g. person name, KPI, or evaluation question).
        n_hops: Number of hops for graph traversal (default: 4).

    Returns:
        Semantic tree text describing the knowledge subgraph.
    """
    try:
        from datacloud_knowledge import nl_to_semantic_tree

        result = await asyncio.to_thread(nl_to_semantic_tree, query, n_hops=n_hops)
    except Exception as e:
        logger.error("nl_to_semantic_tree failed: %s", e)
        return f"(查询失败: {e})"
    return result
