"""TermResolver 测试。"""

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
    loader = TermLoader.from_mapping({
        "status.code": [{"code": "TODO", "label": "待办"}, {"code": "DONE", "label": "已完成"}],
    })
    resolver = TermResolver(term_loader=loader)
    field_specs = [
        ObjectViewField(name="status", type="string", term_set="status.code"),
        ObjectViewField(name="name", type="string", term_set=None),
    ]
    values = {"status": "待办", "name": "测试"}
    result = resolver.resolve_fields(values, field_specs)
    assert result["status"] == "TODO"
    assert result["name"] == "测试"
