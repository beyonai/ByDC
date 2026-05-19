"""DeepAgent BI 示例入口。"""
from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.local_shell import LocalShellBackend
from langchain_anthropic import ChatAnthropic

from tools.datacloud_tool import build_datacloud_tool
from tools.ontology_search_tool import build_ontology_search_tool


def create_bi_agent():  # type: ignore[return]
    """创建并返回 DataCloud BI DeepAgent。"""
    base_dir = Path(os.environ.get("DEEPAGENT_BI_DIR", "."))
    owl_docs_dir = base_dir / "owl_docs"
    resource_dir = Path(os.environ.get("OWL_RESOURCE_DIR", str(base_dir / "owl_resources")))

    model = ChatAnthropic(
        model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.environ.get("LLM_URL") or None,
        temperature=0,
    )
    tools = [
        build_ontology_search_tool(owl_docs_dir),
        build_datacloud_tool(resource_dir),
    ]
    return create_deep_agent(
        model=model,
        memory=["/AGENTS.md"],
        skills=["/skills"],
        tools=tools,
        subagents=[],
        backend=LocalShellBackend(root_dir=base_dir, virtual_mode=True, inherit_env=True),
    )


def make_graph():  # type: ignore[return]
    """langgraph dev 入口。"""
    return create_bi_agent()


def make_graph():  # type: ignore[return]
    """langgraph dev 入口。"""
    return create_bi_agent()
