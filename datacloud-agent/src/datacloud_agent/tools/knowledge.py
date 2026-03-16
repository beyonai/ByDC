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

_knowledge_service: Any | None = None


def _tree_to_text(tree_dict: dict[str, Any], prefix: str = "", is_last: bool = True) -> str:
    """将树形字典转为可读文本"""
    connector = "└── " if is_last else "├── "
    relation_str = f"[{tree_dict.get('relation', '')}] -> " if tree_dict.get("relation") else ""
    name = tree_dict.get("name", "")
    node_type = tree_dict.get("node_type", "")
    lines = [f"{prefix}{connector}{relation_str}{name} [{node_type}]"]
    new_prefix = prefix + ("    " if is_last else "│   ")
    props = tree_dict.get("properties", {})
    if props:
        lines.append(f"{new_prefix}├── 属性:")
        for k, v in list(props.items())[:-1]:
            vstr = str(v)[:100] + "..." if len(str(v)) > 100 else str(v)
            lines.append(f"{new_prefix}│   ├── {k}: {vstr}")
        if props:
            k, v = list(props.items())[-1]
            vstr = str(v)[:100] + "..." if len(str(v)) > 100 else str(v)
            lines.append(f"{new_prefix}│   └── {k}: {vstr}")
    children = tree_dict.get("children", [])
    for i, child in enumerate(children):
        lines.append(_tree_to_text(child, new_prefix, i == len(children) - 1))
    return "\n".join(lines)


def _get_knowledge_service() -> Any | None:
    global _knowledge_service
    if _knowledge_service is not None:
        return _knowledge_service
    try:
        from datacloud_agent.config.env import KnowledgeSettings

        cfg = KnowledgeSettings()
        if not cfg.graph_files_list:
            logger.warning(
                "DATACLOUD_KNOWLEDGE_GRAPH_FILES not configured; search_knowledge returns empty."
            )
            return None
        from datacloud_knowledge_service import KnowledgeGraphQuery

        svc = KnowledgeGraphQuery(
            graph_files=cfg.graph_files_list,
            default_hops=cfg.default_hops,
        )
        _knowledge_service = svc
        return _knowledge_service
    except Exception as e:
        logger.warning("Failed to init KnowledgeGraphQuery: %s", e)
        return None


@tool
async def search_knowledge(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search the enterprise knowledge graph for relevant context.

    Queries the knowledge graph to retrieve entities, relationships, and KPI definitions.
    For example, "王小明优秀吗" (Is Wang Xiaoming excellent?) returns the person entity,
    their KPI associations, and evaluation criteria needed to determine excellence.

    Args:
        query: Natural-language search query (e.g. person name, KPI, or evaluation question).
        top_k: Maximum number of knowledge snippets to return.

    Returns:
        List of ``{title, content, source}`` dicts.
    """
    service = _get_knowledge_service()
    if service is None:
        return []
    try:
        result = await asyncio.to_thread(service.query, query, None)
    except Exception as e:
        logger.error("KnowledgeGraphQuery.query failed: %s", e)
        return []
    snippets = []
    for subgraph in result.get("results", [])[:top_k]:
        center = subgraph.get("center_entity", {})
        title = f"{center.get('name', '')} 相关子图"
        tree_dict = subgraph.get("tree")
        content = _tree_to_text(tree_dict) if tree_dict else "(无树形结构)"
        snippets.append({"title": title, "content": content, "source": "knowledge_graph"})
    return snippets
