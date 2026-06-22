"""Task #6：验证 available_skills XML 注入链路废弃 + llm_config 写入 extras。"""

from __future__ import annotations

from pathlib import Path

_GRAPH_BUILDER = Path(
    "packages/datacloud-analysis/src/datacloud_analysis/orchestration/graph_builder.py"
)
_ONTOLOGY_AGENT = Path("packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py")


class TestXmlInjectionRemoved:
    def test_graph_builder_no_available_skills_injection(self) -> None:
        """graph_builder.py 不应再有 available_skills XML 注入（L470-472 已删除）。"""
        src = _GRAPH_BUILDER.read_text(encoding="utf-8")
        assert "available_skills_xml_v04" not in src, (
            "graph_builder.py 仍含 available_skills_xml_v04，需删除"
        )

    def test_ontology_agent_no_build_available_skills_xml_call(self) -> None:
        """ontology_agent.py 不应再调用 build_available_skills_xml。"""
        src = _ONTOLOGY_AGENT.read_text(encoding="utf-8")
        assert "build_available_skills_xml" not in src, (
            "ontology_agent.py 仍调用 build_available_skills_xml，需删除"
        )

    def test_ontology_agent_no_scan_skill_catalog_for_xml(self) -> None:
        """ontology_agent.py 中 scan_skill_catalog 不应再用于生成 XML（extras['available_skills']）。"""
        src = _ONTOLOGY_AGENT.read_text(encoding="utf-8")
        assert '_effective_extras["available_skills"]' not in src, (
            "ontology_agent.py 仍向 extras 写入 available_skills，需删除"
        )


class TestLlmConfigInExtras:
    def test_ontology_agent_writes_llm_config_to_extras(self) -> None:
        """ontology_agent.py _iter_events 应将 llm_config 写入 _effective_extras。"""
        src = _ONTOLOGY_AGENT.read_text(encoding="utf-8")
        assert '_effective_extras["llm_config"]' in src, (
            "ontology_agent.py 未将 llm_config 写入 _effective_extras，sub_agent 将无法获取 LLM 配置"
        )
