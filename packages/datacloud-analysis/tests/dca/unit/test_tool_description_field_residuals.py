"""T13-1 ~ T13-4：StructuredTool description 中字段键名引导检测。

背景（方向 B）：
    Schema 属性名统一改回 `field`，description 明确说明可填中文名或字段编码。
    LLM 读取 description 的优先级高于 Schema，因此 description 中的引导文字
    必须准确反映键名为 `field`，并说明两种填法均接受。

验证要求：
    1. description 不含旧引导 "**field 统一使用字段编码（field_code）**"（已废弃）
    2. description 不含 "**参数字段统一使用 field_name_cn**"（旧方向 A 写法）
    3. description 含 "field"（键名）相关引导
"""

from __future__ import annotations

# ── 辅助 ──────────────────────────────────────────────────────────────────────


class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
        filter_ops: list[str] | None = None,
        group_ops: list[str] | None = None,
        aggregate_ops: list[str] | None = None,
        analytic_role: str = "dimension",
        analytic_kind: str = "name",
        property_kind: str = "physical",
    ) -> None:
        self.field_code = code
        self.field_name = name
        self.filter_ops = filter_ops or ["eq", "in"]
        self.group_ops = group_ops or []
        self.aggregate_ops = aggregate_ops or []
        self.analytic_role = analytic_role
        self.analytic_kind = analytic_kind
        self.property_kind = property_kind
        self.term_set: str | None = None
        self.field_type = "STRING"
        self.required_filter_group: str | None = None


def _sample_fields() -> list[_FakeField]:
    return [
        _FakeField("stat_date", "统计日期", filter_ops=["eq", "between"]),
        _FakeField(
            "total_revenue",
            "企业总营收（万元）",
            filter_ops=["gt", "lt"],
            aggregate_ops=["sum", "avg"],
            analytic_role="measure",
            analytic_kind="basic_metric",
        ),
        _FakeField(
            "enterprise_level_name",
            "企业等级",
            filter_ops=["eq", "in"],
            group_ops=["direct"],
        ),
    ]


# ── T13-1：query_* description 不含旧 field_code 引导 ────────────────────────


def test_T13_1_query_description_no_old_field_code_instruction() -> None:
    """T13-1：build_query_description 不含旧引导 '**field 统一使用字段编码（field_code）**'。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_description

    desc = build_query_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**field 统一使用字段编码（field_code）**" not in desc, (
        "query description 仍含废弃的旧 field_code 引导\n"
        f"出现位置:\n{desc[:300]}"
    )


# ── T13-2：query_* description 不含旧 field_name_cn 强制引导 ─────────────────


def test_T13_2_query_description_no_field_name_cn_mandate() -> None:
    """T13-2：build_query_description 不含旧方向 A 的 '**参数字段统一使用 field_name_cn**' 引导。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_description

    desc = build_query_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**参数字段统一使用 field_name_cn（字段中文名）**" not in desc, (
        "query description 仍含旧方向 A 的 field_name_cn 强制引导，应改为 field\n"
        f"出现位置:\n{desc[:300]}"
    )


# ── T13-3：compute_* description 不含旧 field_code 引导 ──────────────────────


def test_T13_3_compute_description_no_old_field_code_instruction() -> None:
    """T13-3：build_compute_description 不含旧引导 '**field 统一使用字段编码（field_code）**'。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_description

    desc = build_compute_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**field 统一使用字段编码（field_code）**" not in desc, (
        "compute description 仍含废弃的旧 field_code 引导\n"
        f"出现位置:\n{desc[:300]}"
    )


# ── T13-4：compute_* description 不含旧 field_name_cn 强制引导 ───────────────


def test_T13_4_compute_description_no_field_name_cn_mandate() -> None:
    """T13-4：build_compute_description 不含旧方向 A 的 '**参数字段统一使用 field_name_cn**' 引导。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_description

    desc = build_compute_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**参数字段统一使用 field_name_cn（字段中文名）**" not in desc, (
        "compute description 仍含旧方向 A 的 field_name_cn 强制引导，应改为 field\n"
        f"出现位置:\n{desc[:300]}"
    )
