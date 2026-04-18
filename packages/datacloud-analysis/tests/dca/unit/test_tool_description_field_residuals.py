"""T13-1 ~ T13-4：StructuredTool description 中 field 参数名残留检测。

Bug 描述：
    query_*/compute_* 工具的 description 文字写着
    "**field 统一使用字段编码（field_code）**"，
    LLM 读取 description 的优先级高于 Schema，因此
    不管 Schema 属性名改成什么，LLM 都会生成 field 键名。

修复要求：
    将两处 description 中的
      "**field 统一使用字段编码（field_code）**"
    改为
      "**参数字段统一使用 field_name_cn（字段中文名）**"
    或等价表述，确保 LLM 在阅读 description 时得到正确的键名引导。
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


# ── T13-1：query_* description 不含旧 field 键名引导 ─────────────────────────


def test_T13_1_query_description_no_field_code_instruction() -> None:
    """T13-1：build_query_description 生成的 description 不得含
    '**field 统一使用字段编码（field_code）**' 旧引导文字。
    """
    from datacloud_data_sdk.virtual_action.generator import build_query_description

    desc = build_query_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**field 统一使用字段编码（field_code）**" not in desc, (
        "query description 仍含旧 field 键名引导，LLM 会优先使用 field 而非 field_name_cn\n"
        f"出现位置:\n{desc[:300]}"
    )


# ── T13-2：query_* description 含 field_name_cn 键名引导 ─────────────────────


def test_T13_2_query_description_mentions_field_name_cn() -> None:
    """T13-2：build_query_description 生成的 description 应明确提及 field_name_cn。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_description

    desc = build_query_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "field_name_cn" in desc, (
        "query description 未包含 field_name_cn 引导，LLM 无从得知新键名\n"
        f"当前 description 片段:\n{desc[:300]}"
    )


# ── T13-3：compute_* description 不含旧 field 键名引导 ───────────────────────


def test_T13_3_compute_description_no_field_code_instruction() -> None:
    """T13-3：build_compute_description 生成的 description 不得含
    '**field 统一使用字段编码（field_code）**' 旧引导文字。
    """
    from datacloud_data_sdk.virtual_action.generator import build_compute_description

    desc = build_compute_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "**field 统一使用字段编码（field_code）**" not in desc, (
        "compute description 仍含旧 field 键名引导，LLM 会优先使用 field 而非 field_name_cn\n"
        f"出现位置:\n{desc[:300]}"
    )


# ── T13-4：compute_* description 含 field_name_cn 键名引导 ───────────────────


def test_T13_4_compute_description_mentions_field_name_cn() -> None:
    """T13-4：build_compute_description 生成的 description 应明确提及 field_name_cn。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_description

    desc = build_compute_description("企业分析", "企业综合分析视图", _sample_fields())

    assert "field_name_cn" in desc, (
        "compute description 未包含 field_name_cn 引导，LLM 无从得知新键名\n"
        f"当前 description 片段:\n{desc[:300]}"
    )
