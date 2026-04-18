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
