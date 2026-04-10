"""
测试 DatacloudOutputMiddleware
"""

import json
from unittest.mock import Mock

from langchain.agents.middleware.types import AgentMiddleware

from datacloud_analysis.middlewares.datacloud_output import (
    DatacloudOutputMiddleware,
    _build_6001_format,
    _normalize_emit_result_data,
)


class TestDatacloudOutputMiddleware:
    """测试 DataCloud 输出中间件"""

    def test_inherits_agent_middleware(self):
        """测试继承自 AgentMiddleware"""
        middleware = DatacloudOutputMiddleware()
        assert isinstance(middleware, AgentMiddleware)

    def test_middleware_initialization(self):
        """测试中间件初始化"""
        middleware = DatacloudOutputMiddleware()
        assert middleware.gateway_context is None

    def test_middleware_with_gateway_context(self):
        """测试带 gateway_context 的初始化"""
        mock_gateway = Mock()
        middleware = DatacloudOutputMiddleware(gateway_context=mock_gateway)
        assert middleware.gateway_context == mock_gateway

    def test_has_emit_result_tool(self):
        """测试提供 emit_result 工具"""
        middleware = DatacloudOutputMiddleware()
        assert len(middleware.tools) == 1
        assert middleware.tools[0].name == "emit_result"

    def test_emit_result_text(self):
        """测试输出纯文本结果"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        result = emit_result.invoke(
            {
                "result_type": "text",
                "answer": "操作已完成",
            }
        )

        assert "已输出结果" in result

    def test_emit_result_query_result(self):
        """测试输出查询结果"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        result = emit_result.invoke(
            {
                "result_type": "query_result",
                "answer": "找到3个客户",
                "data": {
                    "columns": ["id", "name"],
                    "rows": [[1, "张三"], [2, "李四"], [3, "王五"]],
                },
            }
        )

        assert "已输出结果" in result

    def test_emit_result_query_result_data_as_json_string(self):
        """query_result 的 data 为 JSON 字符串时应解析后正常输出"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        payload = {"columns": ["id"], "rows": [[1]]}
        result = emit_result.invoke(
            {
                "result_type": "query_result",
                "answer": "一行",
                "data": json.dumps(payload, ensure_ascii=False),
            }
        )

        assert "已输出结果" in result

    def test_emit_result_data_invalid_json_string(self):
        """data 为非法 JSON 字符串时应返回失败信息且不抛异常"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        result = emit_result.invoke(
            {
                "result_type": "query_result",
                "answer": "测试",
                "data": "{not json",
            }
        )

        assert "输出失败" in result

    def test_normalize_emit_result_data(self):
        """_normalize_emit_result_data 行为"""
        assert _normalize_emit_result_data(None) is None
        assert _normalize_emit_result_data({}) == {}
        assert _normalize_emit_result_data('{"a": 1}') == {"a": 1}
        assert _normalize_emit_result_data("  ") is None

    def test_emit_result_csv_file(self):
        """测试输出 CSV 文件"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        result = emit_result.invoke(
            {
                "result_type": "csv_file",
                "answer": "已导出数据",
                "file_path": "/tmp/export.csv",
            }
        )

        assert "已输出结果" in result

    def test_emit_result_json(self):
        """测试输出 JSON 数据"""
        middleware = DatacloudOutputMiddleware()
        emit_result = middleware.tools[0]

        result = emit_result.invoke(
            {
                "result_type": "json",
                "answer": "数据已准备",
                "data": {"key": "value", "count": 42},
            }
        )

        assert "已输出结果" in result

    def test_build_6001_format_text(self):
        """测试构建文本格式"""
        output = _build_6001_format(result_type="text", answer="测试答案")

        assert output["type"] == "result"
        assert output["result_type"] == "text"
        assert output["answer"] == "测试答案"

    def test_build_6001_format_query_result(self):
        """测试构建查询结果格式"""
        output = _build_6001_format(
            result_type="query_result",
            answer="找到数据",
            data={"columns": ["id", "name"], "rows": [[1, "张三"]]},
        )

        assert output["type"] == "result"
        assert output["result_type"] == "query_result"
        assert output["answer"] == "找到数据"
        assert "data" in output
        assert output["data"]["columns"] == ["id", "name"]
        assert output["data"]["rows"] == [[1, "张三"]]
        assert output["data"]["total"] == 1

    def test_build_6001_format_csv_file(self):
        """测试构建 CSV 文件格式"""
        output = _build_6001_format(
            result_type="csv_file",
            answer="文件已生成",
            file_path="/tmp/test.csv",
        )

        assert output["type"] == "result"
        assert output["result_type"] == "csv_file"
        assert output["file_path"] == "/tmp/test.csv"

    def test_build_6001_format_json(self):
        """测试构建 JSON 格式"""
        output = _build_6001_format(
            result_type="json",
            answer="JSON 数据",
            data={"test": "data"},
        )

        assert output["type"] == "result"
        assert output["result_type"] == "json"
        assert output["data"] == {"test": "data"}
