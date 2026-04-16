"""默认内置工具列表契约测试。

规则：
- read_file / ask_user 是默认工具
- write_code / write_file / execute_code 不在默认工具列表中
"""

from __future__ import annotations


def _get_builtin_tool_names() -> list[str]:
    from datacloud_analysis.orchestration.execution.node import _BUILTIN_TOOLS

    return [t.name for t in _BUILTIN_TOOLS]


def test_read_file_is_builtin() -> None:
    assert "read_file" in _get_builtin_tool_names()


def test_ask_user_is_builtin() -> None:
    assert "ask_user" in _get_builtin_tool_names()


def test_write_file_is_not_builtin() -> None:
    assert "write_file" not in _get_builtin_tool_names()


def test_write_code_is_not_builtin() -> None:
    assert "write_code" not in _get_builtin_tool_names()


def test_execute_code_is_not_builtin() -> None:
    assert "execute_code" not in _get_builtin_tool_names()
