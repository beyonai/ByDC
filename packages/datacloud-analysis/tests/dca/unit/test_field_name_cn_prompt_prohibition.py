"""Prompt contract checks for compute field-key guidance."""

from __future__ import annotations


def _extract_compute_section(prompt: str) -> str:
    start = prompt.find("## compute 统计工具参数规则")
    assert start != -1, "Prompt 缺少 compute 统计工具参数规则段落"
    end = prompt.find("##", start + 1)
    return prompt[start:end] if end != -1 else prompt[start:]


def test_T12_1_prompt_uses_field_key_in_metrics_dimensions() -> None:
    """T12-1: compute 规则应明确使用 field 键。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    compute_section = _extract_compute_section(prompt)

    assert "`field`" in compute_section, "compute 段落未声明 field 键名"
    assert "field_name_cn" not in compute_section, "compute 段落不应要求 field_name_cn 键名"


def test_T12_2_field_rule_present_in_compute_section() -> None:
    """T12-2: field 键规则应出现在 compute 段落本身。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    compute_section = _extract_compute_section(prompt)

    assert "metrics 和 dimensions 中指定字段使用 `field` 键" in compute_section


def test_T12_3_field_rule_mentions_metrics_and_dimensions() -> None:
    """T12-3: field 键规则应同时覆盖 metrics 和 dimensions。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    field_rule = ""
    for line in prompt.splitlines():
        if "使用 `field` 键" in line and "metrics" in line:
            field_rule = line
            break

    assert "metrics" in field_rule, f"field 规则应覆盖 metrics，实际：{field_rule!r}"
    assert "dimensions" in field_rule, f"field 规则应覆盖 dimensions，实际：{field_rule!r}"
