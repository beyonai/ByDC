"""
工具注册测试
"""

import pytest
from unittest.mock import Mock, patch
from datacloud_analysis.tools.registry import (
    register_oql_tools,
    register_core_tools,
    register_all_tools,
    get_tool_by_name,
)


class TestToolRegistry:
    """测试工具注册"""

    def test_register_oql_tools(self):
        """测试注册 OQL 工具"""
        with patch("datacloud_analysis.tools.oql.query_objects") as mock_qo, \
             patch("datacloud_analysis.tools.oql.execute_action") as mock_ea:

            mock_qo.name = "query_objects"
            mock_ea.name = "execute_action"

            tools = register_oql_tools()

            assert len(tools) == 2
            assert mock_qo in tools
            assert mock_ea in tools

    def test_register_core_tools(self):
        """测试注册核心工具"""
        with patch("datacloud_analysis.tools.ask_user.ask_user") as mock_au, \
             patch("datacloud_analysis.tools.code_exec.execute_code") as mock_ce, \
             patch("datacloud_analysis.tools.file_io.read_file") as mock_rf, \
             patch("datacloud_analysis.tools.file_io.write_file") as mock_wf:

            mock_au.name = "ask_user"
            mock_ce.name = "execute_code"
            mock_rf.name = "read_file"
            mock_wf.name = "write_file"

            tools = register_core_tools()

            assert len(tools) == 4
            assert mock_au in tools
            assert mock_ce in tools

    def test_register_all_tools(self):
        """测试注册所有工具"""
        with patch("datacloud_analysis.tools.registry.register_oql_tools") as mock_oql, \
             patch("datacloud_analysis.tools.registry.register_core_tools") as mock_core:

            mock_oql.return_value = [Mock(name="tool1"), Mock(name="tool2")]
            mock_core.return_value = [Mock(name="tool3"), Mock(name="tool4")]

            tools = register_all_tools()

            assert len(tools) == 4
            mock_oql.assert_called_once()
            mock_core.assert_called_once()

    def test_get_tool_by_name_success(self):
        """测试根据名称获取工具（成功）"""
        mock_tool = Mock()
        mock_tool.name = "test_tool"

        with patch("datacloud_analysis.tools.registry.register_all_tools") as mock_all:
            mock_all.return_value = [mock_tool]

            tool = get_tool_by_name("test_tool")

            assert tool == mock_tool

    def test_get_tool_by_name_not_found(self):
        """测试根据名称获取工具（不存在）"""
        with patch("datacloud_analysis.tools.registry.register_all_tools") as mock_all:
            mock_all.return_value = []

            with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
                get_tool_by_name("nonexistent")
