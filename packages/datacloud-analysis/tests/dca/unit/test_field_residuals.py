"""T11-1 ~ T11-4：prompts.py / generator.py 中 field 参数名残留检测。

Bug 描述：
    LLM 仍然生成 "field" 而非 "field_name_cn"，根因是两处文字残留：
    1. prompts.py 第 126 行："`field`（字段中文名）" → 执行 Prompt 优先级最高，直接覆盖 Schema
    2. generator.py _msr_item 中 expr/filters description 文字仍写 "field"
    3. generator.py count_all_item description 写 "不需要 field"

修复要求：
    上述三处的 "field" 全部改为 "field_name_cn"，
    确保 LLM 看到的所有提示（Prompt + Schema description）统一指向 field_name_cn。
"""

from __future__ import annotations

# ── 辅助 ──────────────────────────────────────────────────────────────────────


class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
        aggregate_ops: list[str] | None = None,
        analytic_role: str = "measure",
        analytic_kind: str = "basic_metric",
    ) -> None:
        self.field_code = code
        self.field_name = name
        self.filter_ops: list[str] = []
        self.group_ops: list[str] = []
        self.aggregate_ops = aggregate_ops or ["sum", "count_distinct"]
        self.analytic_role = analytic_role
        self.analytic_kind = analytic_kind
        self.property_kind = "physical"
        self.term_set: str | None = None
        self.field_type = "DECIMAL"
        self.required_filter_group: str | None = None


def _metric_fields() -> list[_FakeField]:
    return [
        _FakeField("total_revenue", "管理网格总营收（万元）", ["sum", "avg", "count_distinct"]),
        _FakeField("enterprise_id", "企业唯一ID", ["count_distinct"]),
    ]


# ── T11-1：执行 Prompt 不再包含 `field` 参数名引导 ────────────────────────────


def test_T11_1_execution_prompt_no_bare_field_in_metrics_rule() -> None:
    """T11-1（最高优先级）：执行 Prompt 的 compute metrics 规则应使用 field_name_cn，不得写 `field`。

    残留文字（prompts.py 第 126 行）：
        "- 调用 compute_{对象编码} 时，`metrics` 数组每项必须包含：`field`（字段中文名）、..."
    该行对 LLM 的影响强于 Schema，直接导致 LLM 忽略 Schema 中 field_name_cn 的改名。
    """
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    # 不允许出现裸 `field`（反引号包裹的 field 参数名）作为 metrics 字段键名引导
    # 精确匹配问题文字
    assert "`field`（字段中文名）" not in prompt, (
        "执行 Prompt 仍含 '`field`（字段中文名）' — LLM 会优先遵循 Prompt 而忽略 Schema 改名\n"
        "出现位置: prompts.py compute metrics 规则行"
    )

    # 应改为 field_name_cn
    assert "field_name_cn" in prompt, (
        "执行 Prompt 未包含 field_name_cn 参数名引导，LLM 无从得知新键名"
    )


def test_T11_1b_execution_prompt_metrics_rule_mentions_field_name_cn() -> None:
    """T11-1b：compute metrics 规则行明确写出 field_name_cn。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")

    # metrics 规则中必须提及 field_name_cn
    # 检查 compute 相关段落里有 field_name_cn
    assert "field_name_cn" in prompt and "metrics" in prompt, (
        "执行 Prompt 缺少 compute metrics 的 field_name_cn 说明"
    )


# ── T11-2：_msr_item 的 expr description 不再提及裸 field ────────────────────


def test_T11_2_msr_item_expr_description_no_bare_field() -> None:
    """T11-2：MetricItem 的 expr 属性 description 应写 field_name_cn，不再出现'与 field 互斥'。

    残留文字（generator.py _msr_item）：
        "description": "公式表达式（与 field 互斥），可填中文运算式..."
    """
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    # 找普通指标项（有 expr 属性的）
    items_with_expr = [item for item in metric_items if "expr" in item.get("properties", {})]
    assert items_with_expr, "没有含 expr 的 MetricItem"

    for item in items_with_expr:
        expr_desc = item["properties"]["expr"].get("description", "")
        assert "与 field 互斥" not in expr_desc, (
            f"expr description 仍含 '与 field 互斥'，LLM 会误认为键名是 field: {expr_desc!r}"
        )
        assert "field_name_cn" in expr_desc, (
            f"expr description 应写 '与 field_name_cn 互斥': {expr_desc!r}"
        )


# ── T11-3：_msr_item 的 filters description 不再提及裸 field ─────────────────


def test_T11_3_msr_item_filters_description_no_bare_field() -> None:
    """T11-3：MetricItem 的 filters 属性 description 应写 field_name_cn，不再出现 'field/value'。

    残留文字（generator.py _msr_item）：
        "description": "条件聚合过滤（CASE WHEN），field/value 可填中文..."
    """
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    items_with_filters = [item for item in metric_items if "filters" in item.get("properties", {})]
    assert items_with_filters, "没有含 filters 的 MetricItem"

    for item in items_with_filters:
        filters_desc = item["properties"]["filters"].get("description", "")
        # "field/value" 这种写法暗示键名是 field
        assert "field/value" not in filters_desc, (
            f"filters description 仍含 'field/value'，LLM 会误认为键名是 field: {filters_desc!r}"
        )
        assert "field_name_cn" in filters_desc, (
            f"filters description 应写 field_name_cn: {filters_desc!r}"
        )


# ── T11-4：count_all_item description 不再提及裸 field ───────────────────────


def test_T11_4_count_all_item_description_no_bare_field() -> None:
    """T11-4：count_all_item description 应写 field_name_cn，不再出现'不需要 field'。

    残留文字（generator.py）：
        "description": "内建行数统计，不需要 field"
    """
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    # count_all_item: agg 有 const: "count_all"
    count_all_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("const") == "count_all"
    ]
    assert count_all_items, "没有找到 count_all_item"

    for item in count_all_items:
        desc = item.get("description", "")
        assert "不需要 field" not in desc, f"count_all description 仍含 '不需要 field': {desc!r}"
        # 改为 field_name_cn 或表述为"无需指定字段"
        assert "field_name_cn" in desc or "无需指定字段" in desc, (
            f"count_all description 应写 field_name_cn 或'无需指定字段': {desc!r}"
        )
