"""TermResolver 测试。"""

from datacloud_data_sdk.ontology.models import OntologyField
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import ObjectViewField, ObjectViewFunctionParam
from datacloud_data_sdk.plan.term_resolver import TermResolver


def test_resolve_params_enum() -> None:
    loader = TermLoader.from_mapping(
        {
            "status.code": [
                {"code": "TODO", "label": "待办"},
                {"code": "DONE", "label": "已完成"},
            ],
        }
    )
    resolver = TermResolver(loader)
    specs = [
        ObjectViewFunctionParam("status", "状态", "STRING", "IN", term_set="status.code"),
    ]
    result = resolver.resolve_params({"status": "待办"}, specs)
    assert result["status"] == "TODO"


def test_resolve_params_enum_list() -> None:
    """resolve_params 支持列表参数，逐项解析。"""
    loader = TermLoader.from_mapping(
        {
            "status.code": [
                {"code": "TODO", "label": "待办"},
                {"code": "DONE", "label": "已完成"},
            ],
        }
    )
    resolver = TermResolver(loader)
    specs = [
        ObjectViewFunctionParam("status", "状态", "STRING", "IN", term_set="status.code"),
    ]
    result = resolver.resolve_params({"status": ["待办", "已完成"]}, specs)
    assert result["status"] == ["TODO", "DONE"]


def test_resolve_params_no_loader_passthrough() -> None:
    resolver = TermResolver(None)
    specs = [
        ObjectViewFunctionParam("status", "状态", "STRING", "IN", term_set="status.code"),
    ]
    result = resolver.resolve_params({"status": "待办"}, specs)
    assert result["status"] == "待办"


def test_resolve_params_skips_non_term_params() -> None:
    loader = TermLoader.from_mapping(
        {
            "status.code": [{"code": "TODO", "label": "待办"}],
        }
    )
    resolver = TermResolver(loader)
    specs = [
        ObjectViewFunctionParam("status", "状态", "STRING", "IN", term_set="status.code"),
        ObjectViewFunctionParam("name", "名称", "STRING", "IN", term_set=None),
    ]
    result = resolver.resolve_params({"status": "待办", "name": "张三"}, specs)
    assert result["status"] == "TODO"
    assert result["name"] == "张三"


def test_resolve_fields_resolves_term_bound_values() -> None:
    """resolve_fields 对含 term_set 的 field 做标签→code 解析。"""
    loader = TermLoader.from_mapping(
        {
            "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
        }
    )
    resolver = TermResolver(term_loader=loader)
    field_specs = [
        ObjectViewField(name="status", type="string", term_set="status.code"),
        ObjectViewField(name="name", type="string", term_set=None),
    ]
    values = {"status": "待办", "name": "测试"}
    result = resolver.resolve_fields(values, field_specs)
    assert result["status"] == "TODO"
    assert result["name"] == "测试"


def test_resolve_fields_resolves_term_bound_values_list() -> None:
    """resolve_fields 支持列表值，逐项解析。"""
    loader = TermLoader.from_mapping(
        {
            "status.code": [
                {"code": "TODO", "label": "待办"},
                {"code": "DONE", "label": "已完成"},
            ],
        }
    )
    resolver = TermResolver(term_loader=loader)
    field_specs = [
        ObjectViewField(name="status", type="string", term_set="status.code"),
    ]
    values = {"status": ["待办", "已完成"]}
    result = resolver.resolve_fields(values, field_specs)
    assert result["status"] == ["TODO", "DONE"]


def test_resolve_filter_values_resolves_term_bound_value() -> None:
    """resolve_filter_values 对 filters 中绑定术语的字段 value 做标签→code 解析。"""
    loader = TermLoader.from_mapping(
        {
            "staffName.code": [
                {"code": "E001", "label": "张三"},
                {"code": "E002", "label": "李四"},
            ],
        }
    )
    resolver = TermResolver(term_loader=loader)
    fields = [
        OntologyField("empNo", "员工工号", "STRING", term_set="staffName.code"),
        OntologyField("kpiYear", "考核年份", "INTEGER", term_set=None),
    ]
    filters = {
        "empNo": {"op": "eq", "value": "张三"},
        "kpiYear": {"op": "eq", "value": 2024},
    }
    result = resolver.resolve_filter_values(filters, fields)
    assert result["empNo"]["value"] == "E001"
    assert result["kpiYear"]["value"] == 2024


def test_resolve_filter_values_in_array() -> None:
    """resolve_filter_values 对 in 操作的数组逐项解析。"""
    loader = TermLoader.from_mapping(
        {
            "status.code": [{"code": "A", "label": "状态A"}, {"code": "B", "label": "状态B"}],
        }
    )
    resolver = TermResolver(term_loader=loader)
    fields = [OntologyField("status", "状态", "STRING", term_set="status.code")]
    filters = {"status": {"op": "in", "value": ["状态A", "状态B"]}}
    result = resolver.resolve_filter_values(filters, fields)
    assert result["status"]["value"] == ["A", "B"]


def test_resolve_filter_values_skips_is_null() -> None:
    """resolve_filter_values 对 is_null/is_not_null 不解析 value。"""
    loader = TermLoader.from_mapping({"status.code": [{"code": "A", "label": "A"}]})
    resolver = TermResolver(term_loader=loader)
    fields = [OntologyField("status", "状态", "STRING", term_set="status.code")]
    filters = {"status": {"op": "is_null"}}
    result = resolver.resolve_filter_values(filters, fields)
    assert "value" not in result["status"] or result["status"].get("value") is None


def test_resolve_filter_values_supports_list_protocol() -> None:
    """resolve_filter_values 支持新的 filters 数组协议。"""
    loader = TermLoader.from_mapping(
        {
            "staff.code": [
                {"code": "E001", "label": "张三"},
                {"code": "E002", "label": "李四"},
            ],
        }
    )
    resolver = TermResolver(term_loader=loader)
    fields = [OntologyField("employee", "员工", "STRING", term_set="staff.code")]
    filters = [{"field": "employee", "op": "eq", "value": "张三"}]

    result = resolver.resolve_filter_values(filters, fields)

    assert result[0]["value"] == "E001"


def test_resolve_filter_values_only_resolves_eq_or_in() -> None:
    """只有 eq/in 才做术语转换，其余操作保留原值。"""
    loader = TermLoader.from_mapping(
        {
            "staff.code": [
                {"code": "E001", "label": "张三"},
                {"code": "E002", "label": "李四"},
            ],
        }
    )
    resolver = TermResolver(term_loader=loader)
    fields = [OntologyField("employee", "员工", "STRING", term_set="staff.code")]
    filters = [
        {"field": "employee", "op": "eq", "value": "张三"},
        {"field": "employee", "op": "in", "value": ["张三", "李四"]},
        {"field": "employee", "op": "like", "value": "张三"},
    ]

    result = resolver.resolve_filter_values(filters, fields)

    assert result[0]["value"] == "E001"
    assert result[1]["value"] == ["E001", "E002"]
    assert result[2]["value"] == "张三"
