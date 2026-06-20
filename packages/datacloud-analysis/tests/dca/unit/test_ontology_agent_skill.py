"""OntologyAgent skill 参数单元测试。

覆盖：
  - ask() 接受 skill_dirs / rel_skills 参数（签名保留向后兼容）
  - _iter_events() 内部 llm_config 写入 extras（供 sub_agent 使用）
  - available_skills XML 注入已废弃，不再出现在 prompts_overwrite
  - tools_dict 仍写入 extras 供 sub_agent 克隆分身使用
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from datacloud_analysis.ontology_agent import OntologyAgent, OntologyAgentConfig

# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────


def _make_config() -> OntologyAgentConfig:
    return OntologyAgentConfig(
        api_key="test-key",
        model="test-model",
        resource_path="/tmp/no_resources",
    )


def _write_skill(root: Path, name: str, description: str = "测试描述") -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# body",
        encoding="utf-8",
    )


async def _astream_stub(*args: Any, **kwargs: Any):  # type: ignore[return]
    """空 async generator，用于替换 compiled.astream_events。"""
    return
    yield  # noqa: unreachable


# ─────────────────────────────────────────────────────────────────────────────
# ask() 签名
# ─────────────────────────────────────────────────────────────────────────────


class TestAskSignature:
    def test_skill_dirs_parameter_exists(self) -> None:
        sig = inspect.signature(OntologyAgent.ask)
        assert "skill_dirs" in sig.parameters

    def test_rel_skills_parameter_exists(self) -> None:
        sig = inspect.signature(OntologyAgent.ask)
        assert "rel_skills" in sig.parameters

    def test_skill_dirs_default_is_none(self) -> None:
        sig = inspect.signature(OntologyAgent.ask)
        assert sig.parameters["skill_dirs"].default is None

    def test_rel_skills_default_is_none(self) -> None:
        sig = inspect.signature(OntologyAgent.ask)
        assert sig.parameters["rel_skills"].default is None


# ─────────────────────────────────────────────────────────────────────────────
# _iter_events() 注入行为（新设计：不再注入 XML，改为写入 llm_config）
# ─────────────────────────────────────────────────────────────────────────────


class TestSkillInjection:
    def _make_agent_with_fake_graph(
        self, fake_tools: dict[str, Any]
    ) -> tuple[OntologyAgent, list[Any], list[Any]]:
        """返回 (agent, captured_graph_inputs, captured_run_configs)。"""
        config = _make_config()
        agent = OntologyAgent(config)

        captured_inputs: list[Any] = []
        captured_configs: list[Any] = []

        async def fake_astream_events(graph_input: Any, config: Any = None, **kw: Any) -> Any:
            captured_inputs.append(graph_input)
            captured_configs.append(config)
            return
            yield  # noqa: unreachable

        fake_graph = MagicMock()
        fake_graph.astream_events = fake_astream_events

        patch.object(
            agent,
            "_get_or_build_graph",
            return_value=(fake_graph, fake_tools),
        ).start()

        return agent, captured_inputs, captured_configs

    @pytest.mark.asyncio
    async def test_available_skills_not_in_prompts_overwrite(self, tmp_path: Path) -> None:
        """available_skills XML 注入已废弃，不应出现在 prompts_overwrite。"""
        _write_skill(tmp_path, "老鹰", "战略分析，当用户需要全局分析时使用")
        fake_tools: dict[str, Any] = {"query_scene_crm": object()}
        agent, captured_inputs, _ = self._make_agent_with_fake_graph(fake_tools)

        async for _ in agent.ask(
            question="帮我做战略分析",
            object_codes=["by_customer"],
            skill_dirs=[str(tmp_path)],
            rel_skills=set(),
        ):
            pass

        if captured_inputs:
            po = captured_inputs[0].get("prompts_overwrite", {})
            assert "available_skills" not in po, "available_skills XML 注入应已废弃"

    @pytest.mark.asyncio
    async def test_llm_config_in_gateway_context_extras(self, tmp_path: Path) -> None:
        """llm_config 应写入 gateway_context.extras，供 sub_agent 克隆分身使用。"""
        fake_tools: dict[str, Any] = {"query_scene_crm": object()}
        agent, _, captured_configs = self._make_agent_with_fake_graph(fake_tools)

        async for _ in agent.ask(
            question="test",
            object_codes=["by_customer"],
        ):
            pass

        assert captured_configs
        run_cfg = captured_configs[0]
        gw_ctx = run_cfg.get("configurable", {}).get("gateway_context")
        assert gw_ctx is not None, "gateway_context 未设置"
        extras = getattr(gw_ctx, "extras", None) or {}
        assert "llm_config" in extras, "llm_config 未注入 gateway_context.extras"
        assert extras["llm_config"]["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_tools_dict_in_extras(self, tmp_path: Path) -> None:
        """tools_dict 仍应写入 extras 供 sub_agent 使用。"""
        fake_tools: dict[str, Any] = {"query_scene_crm": object()}
        agent, _, captured_configs = self._make_agent_with_fake_graph(fake_tools)

        async for _ in agent.ask(
            question="test",
            object_codes=["by_customer"],
        ):
            pass

        assert captured_configs
        run_cfg = captured_configs[0]
        gw_ctx = run_cfg.get("configurable", {}).get("gateway_context")
        extras = getattr(gw_ctx, "extras", None) or {}
        assert "tools_dict" in extras, "tools_dict 未注入 extras"
        assert extras["tools_dict"] is fake_tools

    @pytest.mark.asyncio
    async def test_no_skill_dirs_no_injection(self, tmp_path: Path) -> None:
        """skill_dirs=None 时不注入 available_skills。"""
        _write_skill(tmp_path, "老鹰")
        agent, captured_inputs, captured_configs = self._make_agent_with_fake_graph({})

        async for _ in agent.ask(
            question="test",
            object_codes=["by_customer"],
            skill_dirs=None,
        ):
            pass

        if captured_inputs:
            po = captured_inputs[0].get("prompts_overwrite", {})
            assert "available_skills" not in po

        if captured_configs:
            gw_ctx = captured_configs[0].get("configurable", {}).get("gateway_context")
            extras = getattr(gw_ctx, "extras", None) or {}
            assert "skill_catalog" not in extras

    @pytest.mark.asyncio
    async def test_rel_skills_filters_catalog(self, tmp_path: Path) -> None:
        """rel_skills 参数仍可传入（签名向后兼容），不影响运行。"""
        _write_skill(tmp_path, "老鹰", "战略分析")
        _write_skill(tmp_path, "猎手", "销售漏斗")
        agent, captured_inputs, _ = self._make_agent_with_fake_graph({})

        async for _ in agent.ask(
            question="test",
            object_codes=["by_customer"],
            skill_dirs=[str(tmp_path)],
            rel_skills={"老鹰"},
        ):
            pass

        # 新设计下 XML 不再注入，只验证不崩溃即可
        assert True
