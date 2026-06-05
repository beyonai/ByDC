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


def test_term_filter_eq_in_value_must_use_listed_term_values() -> None:
    """术语字段 eq/in 过滤值必须来自字段描述或 Schema 给出的具体术语值。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    assert "filters.op 为 eq 或 in" in prompt
    assert "字段描述/Schema 中列出的具体术语值" in prompt
    assert "禁止填写未出现在术语值列表中的同义词、口语词、编码或自造值" in prompt


def test_query_limit_is_omitted_without_explicit_user_count() -> None:
    """用户未明确查询条数时，提示词要求不要填写 limit。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    assert "用户没有明确要求返回条数时，不要填写 limit" in prompt
    assert (
        "只有用户明确提出前 N 条、最多 N 条、返回 N 条、limit N 或分页大小时，才填写 limit"
        in prompt
    )
