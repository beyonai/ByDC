"""T2-1 ~ T2-2：Prompt 变更验收。

对应 §3.3 prompts.py 更新。
"""

from __future__ import annotations

# ── T2-1：旧元字段规则已移除，新规则存在 ────────────────────────────────────────


def test_T2_1_old_meta_fields_removed_new_rules_present() -> None:
    """T2-1：执行 Prompt 不再包含旧三元字段说明，包含 query/complex_conditions 规则。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    # 旧元字段说明应移除
    assert "intent_reason" not in prompt, "Prompt 仍包含旧字段 intent_reason"
    assert "extraction_confidence" not in prompt, "Prompt 仍包含旧字段 extraction_confidence"
    assert "ambiguous_params" not in prompt, "Prompt 仍包含旧字段 ambiguous_params"
    assert "参数提取自检字段" not in prompt, "Prompt 仍包含旧自检字段标题"

    # 新规则应存在
    assert "complex_conditions" in prompt, "Prompt 缺少 complex_conditions 填写规则"
    assert "query" in prompt, "Prompt 缺少 query 必填规则描述"


# ── T2-2：工具命名规则固定，不依赖环境变量 ─────────────────────────────────────


def test_T2_2_tool_naming_hint_fixed_not_env_dependent() -> None:
    """T2-2：_get_query_tool_hint_zh 固定返回统一入口提示，不再读 DATACLOUD_ONTOLOGY_LOAD_MODE。"""
    import os

    from datacloud_analysis.i18n.prompts import get_execution_prompt

    # 无论环境变量如何，都应包含 query_* / compute_* 工具命名规则
    for env_val in ("", "ontology_query", "db_query", "unknown_mode"):
        os.environ["DATACLOUD_ONTOLOGY_LOAD_MODE"] = env_val
        prompt = get_execution_prompt("zh_CN")
        assert "query_" in prompt, (
            f"环境变量 DATACLOUD_ONTOLOGY_LOAD_MODE={env_val!r} 时 Prompt 缺少 query_* 命名规则"
        )
        assert "compute_" in prompt, (
            f"环境变量 DATACLOUD_ONTOLOGY_LOAD_MODE={env_val!r} 时 Prompt 缺少 compute_* 命名规则"
        )

    # 恢复
    os.environ.pop("DATACLOUD_ONTOLOGY_LOAD_MODE", None)


# ── T3 系列：贪心阶段优化验收（§5.1）────────────────────────────────────────────


def test_T3_1_no_double_write_conflict() -> None:
    """T3-1: 字段透传与 complex_conditions 双写冲突已消除（§5.1.2）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "同时将该字段涉及的完整条件写入 complex_conditions" not in prompt, (
        "Prompt 仍含双写冲突文本"
    )


def test_T3_2_no_unknown_field_trigger_in_complex_conditions() -> None:
    """T3-2: complex_conditions 触发条件 2（字段名找不到→写入）已移除（§5.1.1）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "字段名在工具字段列表中找不到精确对应" not in prompt, (
        "Prompt complex_conditions 规则仍含字段名未命中触发条件"
    )


def test_T3_3_has_tool_selection_guidance() -> None:
    """T3-3: 提示词包含贪心选工具引导（本体选择 + query/compute 任务分类）（§5.1.5）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "工具选择引导" in prompt, "Prompt 缺少贪心选工具引导章节"


def test_T3_4_no_legacy_keyword_extraction() -> None:
    """T3-4: 历史遗留的关键词提取逻辑已移除（§5.1.8）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "关键词只能是：名词或名词短语" not in prompt, "Prompt 仍含旧关键词提取逻辑"


def test_T3_5_field_passthrough_independent_from_complex_conditions() -> None:
    """T3-5: Prompt 明确说明字段透传与 complex_conditions 是独立规则（§5.1.2）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "独立规则" in prompt or "不触发 complex_conditions" in prompt, (
        "Prompt 未明确说明字段透传与 complex_conditions 的独立性"
    )
