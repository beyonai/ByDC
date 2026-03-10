"""
Unit tests for tools module.

Tests the 5 atomic business tools and utility functions.
"""

import pytest
from datacloud_agent.core.tools import (
    know,
    query,
    compute,
    render,
    store,
    get_business_tools,
    get_system_prompt,
)


class TestKnowTool:
    """Tests for the know tool."""

    def test_know_basic_query(self):
        """Test basic knowledge retrieval."""
        result = know.invoke({"query": "用户模型"})
        assert "用户模型" in result
        assert "[Knowledge]" in result

    def test_know_returns_string(self):
        """Test that know returns a string."""
        result = know.invoke({"query": "测试"})
        assert isinstance(result, str)

    def test_know_with_empty_query(self):
        """Test know with empty query."""
        result = know.invoke({"query": ""})
        assert isinstance(result, str)

    def test_know_with_long_query(self):
        """Test know with a longer query."""
        query_text = "业务规则引擎的工作原理和配置方式"
        result = know.invoke({"query": query_text})
        assert query_text in result


class TestQueryTool:
    """Tests for the query tool."""

    def test_query_basic(self):
        """Test basic data query."""
        result = query.invoke({"data": "2024年销售额"})
        assert "2024年销售额" in result
        assert "[Query]" in result

    def test_query_returns_string(self):
        """Test that query returns a string."""
        result = query.invoke({"data": "测试"})
        assert isinstance(result, str)

    def test_query_with_sql(self):
        """Test query with SQL-like request."""
        result = query.invoke({"data": "SELECT * FROM users"})
        assert "SELECT * FROM users" in result


class TestComputeTool:
    """Tests for the compute tool."""

    def test_compute_basic(self):
        """Test basic computation."""
        result = compute.invoke({"expression": "1 + 1"})
        assert "1 + 1" in result
        assert "[Compute]" in result

    def test_compute_returns_string(self):
        """Test that compute returns a string."""
        result = compute.invoke({"expression": "sum([1,2,3])"})
        assert isinstance(result, str)

    def test_compute_with_analysis(self):
        """Test compute with analysis request."""
        result = compute.invoke({"expression": "平均增长率"})
        assert "平均增长率" in result


class TestRenderTool:
    """Tests for the render tool."""

    def test_render_basic(self):
        """Test basic rendering."""
        result = render.invoke({"format_type": "chart", "content": "销售额数据"})
        assert "chart" in result
        assert "销售额数据" in result
        assert "[Render]" in result

    def test_render_returns_string(self):
        """Test that render returns a string."""
        result = render.invoke({"format_type": "table", "content": "data"})
        assert isinstance(result, str)

    def test_render_with_different_formats(self):
        """Test render with different format types."""
        formats = ["chart", "table", "markdown", "html"]
        for fmt in formats:
            result = render.invoke({"format_type": fmt, "content": "test"})
            assert fmt in result


class TestStoreTool:
    """Tests for the store tool."""

    def test_store_basic(self):
        """Test basic storage."""
        result = store.invoke({"key": "user_pref", "value": "dark_mode"})
        assert "user_pref" in result
        assert "dark_mode" in result
        assert "[Store]" in result

    def test_store_returns_string(self):
        """Test that store returns a string."""
        result = store.invoke({"key": "test_key", "value": "test_value"})
        assert isinstance(result, str)

    def test_store_with_complex_value(self):
        """Test store with complex value."""
        value = '{"name": "test", "data": [1, 2, 3]}'
        result = store.invoke({"key": "complex_data", "value": value})
        assert value in result


class TestGetBusinessTools:
    """Tests for the get_business_tools function."""

    def test_returns_list(self):
        """Test that get_business_tools returns a list."""
        tools = get_business_tools()
        assert isinstance(tools, list)

    def test_returns_five_tools(self):
        """Test that exactly 5 tools are returned."""
        tools = get_business_tools()
        assert len(tools) == 5

    def test_contains_all_tools(self):
        """Test that all required tools are present."""
        tools = get_business_tools()
        tool_names = [t.name for t in tools]
        assert "know" in tool_names
        assert "query" in tool_names
        assert "compute" in tool_names
        assert "render" in tool_names
        assert "store" in tool_names

    def test_tools_have_invoke_method(self):
        """Test that all returned tools have invoke method."""
        tools = get_business_tools()
        for tool in tools:
            assert hasattr(tool, "invoke"), f"Tool {tool.name} missing invoke method"
            assert callable(tool.invoke), f"Tool {tool.name} invoke is not callable"


class TestGetSystemPrompt:
    """Tests for the get_system_prompt function."""

    def test_returns_string(self):
        """Test that get_system_prompt returns a string."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)

    def test_not_empty(self):
        """Test that system prompt is not empty."""
        prompt = get_system_prompt()
        assert len(prompt) > 0

    def test_mentions_all_tools(self):
        """Test that all tools are mentioned in prompt."""
        prompt = get_system_prompt()
        assert "know" in prompt
        assert "query" in prompt
        assert "compute" in prompt
        assert "render" in prompt
        assert "store" in prompt

    def test_contains_tool_usage_instruction(self):
        """Test that prompt contains tool usage instruction."""
        prompt = get_system_prompt()
        assert "工具" in prompt


class TestToolIntegration:
    """Integration tests for tools working together."""

    def test_all_tools_invocable(self):
        """Test that all tools can be invoked."""
        know.invoke({"query": "test"})
        query.invoke({"data": "test"})
        compute.invoke({"expression": "test"})
        render.invoke({"format_type": "test", "content": "test"})
        store.invoke({"key": "test", "value": "test"})

    def test_tools_have_descriptions(self):
        """Test that all tools have docstrings."""
        tools = get_business_tools()
        for tool in tools:
            assert tool.description is not None
            assert len(tool.description) > 0
