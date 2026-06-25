"""ParamLinkGraph 单元测试 — 红阶段先写测试，再实现。"""

from __future__ import annotations

from datacloud_analysis.tools.param_link_graph import (
    ParamLinkGraph,
    _expand_object_property,
)


class TestExpandObjectProperty:
    def test_no_prefix_expands_with_belong(self):
        assert (
            _expand_object_property("span_id", "ops_langfuse_trace") == "ops_langfuse_trace.span_id"
        )

    def test_double_brace_prefix_expands(self):
        assert (
            _expand_object_property("{{ops_dig_employee}}.agent_id", "ops_langfuse_trace")
            == "ops_dig_employee.agent_id"
        )

    def test_leading_underscore_skipped(self):
        # object_property 以 _ 开头表示内部字段，不参与索引
        result = _expand_object_property("_internal", "ops_langfuse_trace")
        assert result == "ops_langfuse_trace._internal"


class TestParamLinkGraphBuild:
    def _make_tool_pool(self):
        """构造最小 tool_pool mock，模拟 get_spans → get_tool_detail 串联。"""
        return {
            "get_spans": object(),
            "get_tool_detail": object(),
            "validate_jdbc_url": object(),
            "get_dbsource": object(),
        }

    def _make_loader(self, params_map: dict):
        """构造 owl_loader mock。"""

        class MockLoader:
            def get_action_params(self, action_code):
                if action_code in params_map:
                    return params_map[action_code]
                raise KeyError(action_code)

        return MockLoader()

    def test_build_creates_link_for_matching_object_property(self):
        """get_spans 出参 span_id 与 get_tool_detail 入参 span_id 匹配 → 建立串联。"""
        params_map = {
            "get_spans": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [],
                "response_params": [
                    {"field_code": "span_id", "object_property": "span_id"},
                ],
            },
            "get_tool_detail": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [
                    {"param_code": "span_id", "object_property": "span_id"},
                ],
                "response_params": [],
            },
        }
        plg = ParamLinkGraph()
        plg.build(self._make_tool_pool(), self._make_loader(params_map))
        nexts = plg.get_next_tools("get_spans")
        assert "get_tool_detail" in nexts

    def test_build_no_self_link(self):
        """同一工具的出参和入参不建立自链接。"""
        params_map = {
            "get_spans": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [
                    {"param_code": "trace_id", "object_property": "trace_id"},
                ],
                "response_params": [
                    {"field_code": "trace_id", "object_property": "trace_id"},
                ],
            },
        }
        plg = ParamLinkGraph()
        plg.build({"get_spans": object()}, self._make_loader(params_map))
        assert "get_spans" not in plg.get_next_tools("get_spans")

    def test_cross_object_property_link(self):
        """跨对象 {{ops_dig_employee}}.agent_id 正确展开并建立串联。"""
        params_map = {
            "get_agent_diag": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [],
                "response_params": [
                    {"field_code": "agent_id", "object_property": "{{ops_dig_employee}}.agent_id"},
                ],
            },
            "check_config_file_exists": {
                "belong_entity": "ops_dig_employee",
                "request_params": [
                    {"param_code": "agent_id", "object_property": "{{ops_dig_employee}}.agent_id"},
                ],
                "response_params": [],
            },
        }
        plg = ParamLinkGraph()
        plg.build(
            {"get_agent_diag": object(), "check_config_file_exists": object()},
            self._make_loader(params_map),
        )
        assert "check_config_file_exists" in plg.get_next_tools("get_agent_diag")

    def test_get_chain_hint_empty_when_no_active(self):
        plg = ParamLinkGraph()
        assert plg.get_chain_hint([]) == ""

    def test_get_chain_hint_returns_text_for_active_tools(self):
        params_map = {
            "get_spans": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [],
                "response_params": [
                    {"field_code": "span_id", "object_property": "span_id"},
                ],
            },
            "get_tool_detail": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [
                    {"param_code": "span_id", "object_property": "span_id"},
                ],
                "response_params": [],
            },
        }
        plg = ParamLinkGraph()
        plg.build(
            {"get_spans": object(), "get_tool_detail": object()},
            self._make_loader(params_map),
        )
        hint = plg.get_chain_hint(["get_spans"])
        assert "get_tool_detail" in hint
        assert "span_id" in hint

    def test_summary_reports_link_count(self):
        params_map = {
            "get_spans": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [],
                "response_params": [
                    {"field_code": "span_id", "object_property": "span_id"},
                ],
            },
            "get_tool_detail": {
                "belong_entity": "ops_langfuse_trace",
                "request_params": [
                    {"param_code": "span_id", "object_property": "span_id"},
                ],
                "response_params": [],
            },
        }
        plg = ParamLinkGraph()
        plg.build(
            {"get_spans": object(), "get_tool_detail": object()},
            self._make_loader(params_map),
        )
        s = plg.summary()
        assert "1" in s  # 1 条串联关系
