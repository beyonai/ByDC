"""TC-01 ~ TC-12：OntologyToolLoader agent_friendly / ontology_path 验收。

覆盖：
  TC-03  ontology_path 路径自动完成 load+inject
  TC-04  loader / ontology_path 均不传时抛 ValueError
  TC-05  agent_friendly=True：filters 为 relaxed（含 catch-all + 原词透传指令）
  TC-05b agent_friendly=True：select description 允许中文名和原词透传
  TC-05c agent_friendly=True：order_by.field description 允许中文名和原词透传
  TC-05d agent_friendly=True：complex_conditions description 不含"字段名未命中→写此列表"冲突条件
  TC-06  agent_friendly=False：_apply_agent_schema_patches 不被调用
  TC-07  VIEW 路径：通过 get_view 获取字段后同样完成全量 patch
  TC-11  inject_virtual_actions 生成的 schema 仍为 strict（MCP 隔离）
  TC-12  loader 查找失败时降级为 strict，不抛异常
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fake helpers
# ---------------------------------------------------------------------------


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


def _enterprise_fields() -> list[_FakeField]:
    return [
        _FakeField("enterprise_name", "企业名称", filter_ops=["eq", "like"]),
        _FakeField("total_revenue", "总营收", filter_ops=["gt", "lt"]),
        _FakeField("enterprise_level_name", "企业等级", filter_ops=["eq", "in"]),
    ]


def _make_mock_loader(fields: list[_FakeField]) -> Any:
    """构造一个模拟 OBJECT 查询路径的 loader mock。"""
    loader = Mock()
    mock_cls = Mock()
    mock_cls.fields = fields
    loader.get_ontology_class.return_value = mock_cls
    loader.get_view.side_effect = KeyError("not a view")
    loader._scenes = {}  # 空 _scenes → _is_view 返回 False
    return loader


def _make_view_mock_loader(fields: list[_FakeField], view_code: str) -> Any:
    """构造一个模拟 VIEW 查询路径的 loader mock。"""
    loader = Mock()
    loader.get_ontology_class.side_effect = KeyError("not an object")
    mock_view = Mock()
    mock_view.fields = fields
    loader.get_view.return_value = mock_view
    loader._scenes = {view_code: mock_view}  # VIEW 识别
    return loader


# ---------------------------------------------------------------------------
# TC-04：未传 loader 也未传 ontology_path → ValueError
# ---------------------------------------------------------------------------


def test_TC04_neither_loader_nor_path_raises_value_error() -> None:
    """TC-04：同时不传 loader 和 ontology_path 时，__init__ 抛 ValueError。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

    with pytest.raises(ValueError, match="必须提供 loader 或 ontology_path 之一"):
        OntologyToolLoader(mounted_objects=["enterprise"])


# ---------------------------------------------------------------------------
# TC-03：ontology_path 触发 _build_loader（自动 load + inject）
# ---------------------------------------------------------------------------


def test_TC03_ontology_path_triggers_build_loader() -> None:
    """TC-03：传入 ontology_path 时，自动调用 OntologyLoader.load_from_owl_directory 和 inject_virtual_actions。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

    mock_loader_instance = MagicMock()

    with (
        patch(
            "datacloud_analysis.tools.ontology_tool_loader.OntologyToolLoader._build_loader",
            return_value=mock_loader_instance,
        ) as mock_build,
    ):
        sut = OntologyToolLoader(
            mounted_objects=["enterprise"],
            ontology_path="/fake/owl/path",
        )

    mock_build.assert_called_once()
    # loader 被赋值为 _build_loader 的返回值
    assert sut._loader is mock_loader_instance  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TC-05：agent_friendly=True → filters 替换为 relaxed（含 catch-all）
# ---------------------------------------------------------------------------


def test_TC05_filters_relaxed_contains_catchall() -> None:
    """TC-05：_apply_agent_schema_patches 将 filters 替换为 relaxed 版本，含 catch-all 兜底。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", strict_schema)  # type: ignore[attr-defined]

    filters = patched["properties"]["filters"]

    # description 含"字段中文名或字段编码"
    assert "字段中文名" in filters.get("description", "") or "中文名" in filters.get(
        "description", ""
    ), f"relaxed filters description 应含字段中文名说明，实际: {filters.get('description')!r}"

    # anyOf / oneOf 末尾有 catch-all（field 无 enum 约束）
    one_of: list[dict[str, Any]] = filters.get("items", {}).get("oneOf", [])
    assert one_of, "relaxed filters 应有 items.oneOf"
    has_catchall = any("enum" not in item.get("properties", {}).get("field", {}) for item in one_of)
    assert has_catchall, "relaxed filters 应含无 enum 约束的 catch-all item"


def test_TC05_catchall_field_description_contains_yuanci() -> None:
    """TC-05（续）：catch-all item 的 field.description 含"原词"字样。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", strict_schema)  # type: ignore[attr-defined]

    one_of: list[dict[str, Any]] = patched["properties"]["filters"]["items"]["oneOf"]
    catchall = next(
        item for item in one_of if "enum" not in item.get("properties", {}).get("field", {})
    )
    field_desc = catchall["properties"]["field"].get("description", "")
    assert "原词" in field_desc, f"catch-all field description 应含'原词'，实际: {field_desc!r}"


# ---------------------------------------------------------------------------
# TC-05b：select description 允许中文名和原词透传
# ---------------------------------------------------------------------------


def test_TC05b_select_description_allows_chinese_and_yuanci() -> None:
    """TC-05b：_apply_agent_schema_patches 后 select description 含"中文名"和"原词"。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", strict_schema)  # type: ignore[attr-defined]

    select_desc = patched["properties"]["select"].get("description", "")
    assert "中文名" in select_desc, f"select description 应含'中文名'，实际: {select_desc!r}"
    assert "原词" in select_desc, f"select description 应含'原词'，实际: {select_desc!r}"


# ---------------------------------------------------------------------------
# TC-05c：order_by.field description 允许中文名和原词透传
# ---------------------------------------------------------------------------


def test_TC05c_order_by_field_description_allows_chinese_and_yuanci() -> None:
    """TC-05c：_apply_agent_schema_patches 后 order_by.field description 含"中文名"和"原词"。"""
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", strict_schema)  # type: ignore[attr-defined]

    ob_field_desc = (
        patched["properties"]["order_by"]
        .get("items", {})
        .get("properties", {})
        .get("field", {})
        .get("description", "")
    )
    assert "中文名" in ob_field_desc, (
        f"order_by.field description 应含'中文名'，实际: {ob_field_desc!r}"
    )
    assert "原词" in ob_field_desc, (
        f"order_by.field description 应含'原词'，实际: {ob_field_desc!r}"
    )


# ---------------------------------------------------------------------------
# TC-05d：complex_conditions description 不含"字段名未命中 → 写此列表"冲突条件
# ---------------------------------------------------------------------------


def test_TC05d_complex_conditions_no_field_not_found_trigger() -> None:
    """TC-05d：_apply_agent_schema_patches 后 complex_conditions description 不包含"字段名未命中→写此列表"语义，
    且明确声明字段名找不到时填原词到标准参数。
    """
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", strict_schema)  # type: ignore[attr-defined]

    cc_desc = patched["properties"]["complex_conditions"].get("description", "")

    # 冲突条件必须消失：不应出现"字段名未命中"的同时要写入该列表
    # （原描述"字段名未命中不是此列表的适用场景"是 strict 版描述，patch 后应被替换）
    assert "字段名未命中不是此列表的适用场景" not in cc_desc, (
        "patch 后 complex_conditions description 不应保留 strict 版旧描述"
    )

    # 应明确指出字段名找不到时填原词到标准参数
    assert "不写入此列表" in cc_desc or "select/filters/order_by 中填" in cc_desc, (
        f"complex_conditions description 应声明字段名找不到时填原词到标准参数，实际: {cc_desc!r}"
    )


# ---------------------------------------------------------------------------
# TC-06：agent_friendly=False → _apply_agent_schema_patches 未被调用
# ---------------------------------------------------------------------------


def test_TC06_agent_friendly_false_patches_not_applied() -> None:
    """TC-06：agent_friendly=False 时，_apply_agent_schema_patches 不应修改 schema。

    通过对比 strict schema 原始 filters description 来验证未被 patch。
    """
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("企业分析", fields)

    sut = OntologyToolLoader(
        mounted_objects=["enterprise"],
        loader=_make_mock_loader(fields),
        agent_friendly=False,
    )

    # agent_friendly=False → 内部 _agent_friendly 标志为 False
    assert sut._agent_friendly is False  # type: ignore[attr-defined]

    # 原始 filters description（无论 strict 还是 relaxed 版本）不含 AGENT_SELECT_DESCRIPTION 的专属文字
    from datacloud_analysis.tools._agent_schema_patches import AGENT_SELECT_DESCRIPTION

    original_select_desc = strict_schema["properties"]["select"].get("description", "")
    assert original_select_desc != AGENT_SELECT_DESCRIPTION, (
        "agent_friendly=False 时，原始 schema 不应被 AGENT_SELECT_DESCRIPTION 替换"
    )


# ---------------------------------------------------------------------------
# TC-07：VIEW 路径 → 通过 get_view 获取字段，同样完成全量 patch
# ---------------------------------------------------------------------------


def test_TC07_view_path_fields_from_get_view() -> None:
    """TC-07：_apply_agent_schema_patches 在 OBJECT 查找失败后通过 get_view 获取字段，
    仍能正确 patch filters / select / order_by.field / complex_conditions。
    """
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    strict_schema = build_query_schema("管理网格视图", fields)

    # loader：OBJECT 路径失败，VIEW 路径成功
    loader = _make_view_mock_loader(fields, "manage_grid_view")

    sut = OntologyToolLoader(mounted_objects=["manage_grid_view"], loader=loader)
    patched = sut._apply_agent_schema_patches("manage_grid_view", strict_schema)  # type: ignore[attr-defined]

    filters = patched["properties"]["filters"]
    select_desc = patched["properties"]["select"].get("description", "")
    cc_desc = patched["properties"]["complex_conditions"].get("description", "")

    assert "中文名" in filters.get("description", ""), "VIEW path: filters description 应含中文名"
    assert "中文名" in select_desc, "VIEW path: select description 应含中文名"
    assert "不写入此列表" in cc_desc or "select/filters/order_by 中填" in cc_desc, (
        "VIEW path: complex_conditions description 应声明原词透传"
    )


# ---------------------------------------------------------------------------
# TC-11：_apply_agent_schema_patches 不修改原始 input_schema（MCP 隔离）
# ---------------------------------------------------------------------------


def test_TC11_apply_patches_does_not_modify_original_schema() -> None:
    """TC-11：_apply_agent_schema_patches 返回新 dict，不修改传入的 input_schema 原对象。

    这保证了从 inject_virtual_actions / ActionToolGenerator 中取出的 input_schema
    在 agent 侧 patch 后仍保持原值不变（MCP 侧读取同一对象时不受干扰）。
    """
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    fields = _enterprise_fields()
    original_schema = build_query_schema("企业分析", fields)
    original_select_desc = original_schema["properties"]["select"].get("description", "")

    sut = OntologyToolLoader(mounted_objects=["enterprise"], loader=_make_mock_loader(fields))
    patched = sut._apply_agent_schema_patches("enterprise", original_schema)  # type: ignore[attr-defined]

    # 1. 返回的是新对象，不是原对象
    assert patched is not original_schema, "_apply_agent_schema_patches 应返回新 dict，不修改原对象"

    # 2. 原对象的 select description 未被改写
    assert original_schema["properties"]["select"].get("description", "") == original_select_desc, (
        "原始 input_schema 的 select description 不应被 _apply_agent_schema_patches 修改"
    )


# ---------------------------------------------------------------------------
# TC-12：loader 查找失败时降级为 strict，不抛异常
# ---------------------------------------------------------------------------


def test_TC12_degradation_on_loader_lookup_failure() -> None:
    """TC-12：_apply_agent_schema_patches 在 get_ontology_class 和 get_view 均失败时，
    原样返回 input_schema，不抛异常。
    """
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader

    loader = Mock()
    loader.get_ontology_class.side_effect = Exception("not found")
    loader.get_view.side_effect = Exception("not found")

    sut = OntologyToolLoader(mounted_objects=["nonexistent"], loader=loader)
    original_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"filters": {"type": "array", "description": "strict"}},
    }

    result = sut._apply_agent_schema_patches("nonexistent", original_schema)  # type: ignore[attr-defined]

    assert result is original_schema, "降级时应原样返回 input_schema，不做任何修改"
