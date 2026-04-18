"""T12-1 ~ T12-3：执行 Prompt 明确禁止 `field` 键名 + 要求 `field_name_cn`。

Bug 描述：
    LLM 对 metrics/dimensions 使用 `field` 而非 `field_name_cn`，
    原因是 `field_name_cn` 不在 required 里，LLM 回退到训练先验键名 `field`。

修复要求：
    在执行 Prompt 的 compute 工具参数规则中，明确新增一条禁令：
    "metrics 和 dimensions 中指定字段必须使用 `field_name_cn` 键
     （禁止使用旧键名 `field`）"
"""

from __future__ import annotations


# ── T12-1：Prompt 含明确禁止 `field` 键名的规则 ───────────────────────────────


def test_T12_1_prompt_prohibits_field_key_in_metrics_dimensions() -> None:
    """T12-1：执行 Prompt 应明确禁止在 metrics/dimensions 中使用旧键名 `field`。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    assert "禁止使用旧键名 `field`" in prompt, (
        "执行 Prompt 缺少对旧键名 `field` 的明确禁止规则\n"
        "LLM 在 field_name_cn 不在 required 时会回退到训练先验 field"
    )


# ── T12-2：禁令规则位于 compute 工具参数规则段落内 ────────────────────────────


def test_T12_2_prohibition_rule_in_compute_section() -> None:
    """T12-2：禁令应出现在 compute 工具参数规则段落中（而非隐藏在文档末尾）。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    compute_section_start = prompt.find("## compute 统计工具参数规则")
    assert compute_section_start != -1, "Prompt 缺少 compute 统计工具参数规则段落"

    # 找到 compute 段落结束位置（下一个 ## 之前）
    next_section = prompt.find("##", compute_section_start + 1)
    compute_section = (
        prompt[compute_section_start:next_section]
        if next_section != -1
        else prompt[compute_section_start:]
    )

    assert "禁止使用旧键名 `field`" in compute_section, (
        "禁令规则应在 compute 统计工具参数规则段落内，使 LLM 在生成 metrics/dimensions 时能读到\n"
        f"当前 compute 段落内容：\n{compute_section}"
    )


# ── T12-3：禁令规则同时提及 metrics 和 dimensions ────────────────────────────


def test_T12_3_prohibition_mentions_metrics_and_dimensions() -> None:
    """T12-3：禁令规则应同时覆盖 metrics 和 dimensions，不遗漏 dimensions。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    # 找到含禁令的那一行
    prohibition_line = ""
    for line in prompt.splitlines():
        if "禁止使用旧键名 `field`" in line:
            prohibition_line = line
            break

    assert "metrics" in prohibition_line, (
        f"禁令行应覆盖 metrics，实际：{prohibition_line!r}"
    )
    assert "dimensions" in prohibition_line, (
        f"禁令行应覆盖 dimensions，实际：{prohibition_line!r}"
    )
