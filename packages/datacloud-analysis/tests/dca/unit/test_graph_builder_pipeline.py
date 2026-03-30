from __future__ import annotations

from datacloud_analysis.orchestration.graph_builder import build_analysis_graph


def test_graph_builder_uses_five_node_main_pipeline() -> None:
    graph = build_analysis_graph(prompts_overwrite={}, tools={})
    compiled = graph.compile()
    node_names = list(compiled.get_graph().nodes.keys())

    assert "knowledge_enhance" in node_names
    assert "planning" in node_names
    assert "execution" in node_names
    assert "end" in node_names
    assert "intent" not in node_names
    assert "dag" not in node_names
    assert "loop" not in node_names
