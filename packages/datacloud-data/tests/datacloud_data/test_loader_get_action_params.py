"""OntologyLoader.get_action_params() 单元测试。"""
from __future__ import annotations

import pytest
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import (
    OntologyAction,
    OntologyActionParam,
    OntologyClass,
)


def _make_loader_with_action(
    object_code: str,
    action_code: str,
    params: list[OntologyActionParam],
) -> OntologyLoader:
    """构造只含一个对象+一个 action 的 OntologyLoader。"""
    loader = OntologyLoader()
    cls = OntologyClass(
        object_code=object_code,
        object_name=object_code,
        description="",
        source_type="DB",
        fields=[],
        actions=[
            OntologyAction(
                action_code=action_code,
                action_name=action_code,
                description="",
                belong_class=object_code,
                params=params,
                function_refs=[],
                action_type="QUERY",
            )
        ],
    )
    loader._classes[object_code] = cls
    return loader


class TestGetActionParams:
    def test_returns_belong_entity(self):
        loader = _make_loader_with_action("ops_langfuse_trace", "get_spans", [])
        result = loader.get_action_params("get_spans")
        assert result["belong_entity"] == "ops_langfuse_trace"

    def test_in_param_goes_to_request_params(self):
        param = OntologyActionParam(
            param_code="trace_id",
            param_name="trace_id",
            direction="IN",
            param_type="STRING",
            object_property="trace_id",
            json_path="$.requestBody.trace_id",
        )
        loader = _make_loader_with_action("ops_langfuse_trace", "get_spans", [param])
        result = loader.get_action_params("get_spans")
        assert len(result["request_params"]) == 1
        assert len(result["response_params"]) == 0
        rp = result["request_params"][0]
        assert rp["param_code"] == "trace_id"
        assert rp["object_property"] == "trace_id"
        assert rp["json_path"] == "$.requestBody.trace_id"

    def test_out_param_goes_to_response_params(self):
        param = OntologyActionParam(
            param_code="span_id",
            param_name="span_id",
            direction="OUT",
            param_type="STRING",
            object_property="span_id",
            json_path="$.records[].span_id",
        )
        loader = _make_loader_with_action("ops_langfuse_trace", "get_spans", [param])
        result = loader.get_action_params("get_spans")
        assert len(result["response_params"]) == 1
        assert len(result["request_params"]) == 0
        rp = result["response_params"][0]
        assert rp["field_code"] == "span_id"
        assert rp["object_property"] == "span_id"

    def test_mixed_in_out_params(self):
        params = [
            OntologyActionParam(
                param_code="trace_id", param_name="trace_id",
                direction="IN", param_type="STRING",
                object_property="trace_id",
            ),
            OntologyActionParam(
                param_code="span_id", param_name="span_id",
                direction="OUT", param_type="STRING",
                object_property="span_id",
            ),
        ]
        loader = _make_loader_with_action("ops_langfuse_trace", "get_spans", params)
        result = loader.get_action_params("get_spans")
        assert len(result["request_params"]) == 1
        assert len(result["response_params"]) == 1

    def test_empty_object_property_becomes_empty_string(self):
        param = OntologyActionParam(
            param_code="max_chars", param_name="max_chars",
            direction="IN", param_type="INTEGER",
            object_property=None,
        )
        loader = _make_loader_with_action("ops_langfuse_trace", "get_tool_detail", [param])
        result = loader.get_action_params("get_tool_detail")
        rp = result["request_params"][0]
        assert rp["object_property"] == ""

    def test_raises_key_error_for_unknown_action(self):
        loader = OntologyLoader()
        with pytest.raises(KeyError):
            loader.get_action_params("nonexistent_action")

    def test_cross_object_property_preserved(self):
        param = OntologyActionParam(
            param_code="agent_id", param_name="agent_id",
            direction="OUT", param_type="STRING",
            object_property="{{ops_dig_employee}}.agent_id",
        )
        loader = _make_loader_with_action("ops_langfuse_trace", "get_agent_diag", [param])
        result = loader.get_action_params("get_agent_diag")
        rp = result["response_params"][0]
        assert rp["object_property"] == "{{ops_dig_employee}}.agent_id"
