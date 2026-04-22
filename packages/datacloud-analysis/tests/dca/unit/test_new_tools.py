"""Tests for new atomic tool files: ask_user and file_io."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ask_user tool
# ---------------------------------------------------------------------------


class TestAskUserTool:
    def test_ask_user_tool_has_correct_name(self) -> None:
        from datacloud_analysis.tools.ask_user import ask_user

        assert ask_user.name == "ask_user"

    def test_ask_user_not_injected_with_reason_schema(self) -> None:
        """ask_user should NOT have a reason field auto-injected (it has its own)."""
        from datacloud_analysis.tools.ask_user import ask_user

        # The schema should already have 'reason' as a field
        schema = ask_user.args_schema
        assert schema is not None
        if hasattr(schema, "model_fields"):
            assert "reason" in schema.model_fields
        else:
            assert "reason" in schema


# ---------------------------------------------------------------------------
# read_file / write_file tools
# ---------------------------------------------------------------------------


class TestFileIOTools:
    @pytest.mark.asyncio
    async def test_read_file_returns_content(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world", encoding="utf-8")

            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await read_file.ainvoke({"path": "test.txt"})

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_missing_returns_error(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(
                os.environ,
                {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir},
            ),
        ):
            result = await read_file.ainvoke({"path": "nonexistent.txt"})

        assert "错误" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_write_file_creates_file(self) -> None:
        from datacloud_analysis.tools.file_io import write_file

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(
                os.environ,
                {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir},
            ),
        ):
            result = await write_file.ainvoke({"path": "output.txt", "content": "data"})
            written = await asyncio.to_thread(Path(tmpdir, "output.txt").read_text)

        assert result["success"] is True
        assert written == "data"

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self) -> None:
        """Accessing files outside workspace_dir should return an error."""
        from datacloud_analysis.tools.file_io import read_file

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(
                os.environ,
                {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir},
            ),
        ):
            result = await read_file.ainvoke({"path": "../../etc/passwd"})

        assert "错误" in result or "error" in result.lower() or "outside" in result.lower()


# ---------------------------------------------------------------------------
# Gateway file_manager 委托路径测试（_context 注入）
# ---------------------------------------------------------------------------


def _make_mock_context(
    read_return: dict[str, Any] | None = None,
    write_return: dict[str, Any] | None = None,
) -> MagicMock:
    """构造一个最小的 mock gateway_context，file_manager 方法均为 AsyncMock。"""
    file_manager = MagicMock()
    file_manager.read_file = AsyncMock(return_value=read_return or {})
    file_manager.write_file = AsyncMock(return_value=write_return or {})

    session_manager = MagicMock()
    session_manager.file_manager = file_manager

    agent_runtime_state = MagicMock()
    agent_runtime_state.session_manager = session_manager

    ctx = MagicMock()
    ctx.agent_runtime_state = agent_runtime_state
    return ctx


async def _invoke_with_context(tool_func: Any, params: dict[str, Any], ctx: MagicMock) -> Any:
    """模拟 _invoke_tool_with_runtime_context 的注入行为：直接调用底层 coroutine，注入 _context。"""
    invoke_params = dict(params)
    invoke_params["_context"] = ctx
    coroutine = getattr(tool_func, "coroutine", None)
    if coroutine is not None:
        return await coroutine(**invoke_params)
    func = getattr(tool_func, "func", None)
    if func is not None:
        return func(**invoke_params)
    raise RuntimeError(f"Cannot find callable on {tool_func}")


class TestFileIOToolsWithGateway:
    """验收用例 1-3：read_file / write_file 委托 Gateway FileManager。"""

    @pytest.mark.asyncio
    async def test_read_file_delegates_to_file_manager(self) -> None:
        """用例 1：read_file 委托 gateway FileManager 读取文件。"""
        from datacloud_analysis.tools.file_io import read_file

        ctx = _make_mock_context(read_return={"success": True, "data": {"content": "hello"}})
        result = await _invoke_with_context(read_file, {"path": "output/result.txt"}, ctx)

        assert result == "hello"
        ctx.agent_runtime_state.session_manager.file_manager.read_file.assert_called_once_with(
            "output/result.txt", encoding="utf-8"
        )

    @pytest.mark.asyncio
    async def test_write_file_delegates_to_file_manager(self) -> None:
        """用例 2：write_file 委托 gateway FileManager 写入文件。"""
        from datacloud_analysis.tools.file_io import write_file

        ctx = _make_mock_context(
            write_return={
                "success": True,
                "message": "ok",
                "data": {"path": "temp/out.txt", "bytes_written": 4},
            }
        )
        result = await _invoke_with_context(
            write_file, {"path": "temp/out.txt", "content": "data"}, ctx
        )

        assert result["success"] is True
        ctx.agent_runtime_state.session_manager.file_manager.write_file.assert_called_once_with(
            "temp/out.txt", "data", encoding="utf-8"
        )

    @pytest.mark.asyncio
    async def test_read_file_returns_error_string_on_failure(self) -> None:
        """用例 3：file_manager 返回错误时 read_file 正确传递错误信息，不抛异常。"""
        from datacloud_analysis.tools.file_io import read_file

        ctx = _make_mock_context(
            read_return={"success": False, "error": "File not found: output/x.txt"}
        )
        result = await _invoke_with_context(read_file, {"path": "output/x.txt"}, ctx)

        assert "File not found" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_read_file_falls_back_to_local_when_context_is_none(self) -> None:
        """用例 4：_context 为 None 时降级本地实现。"""
        from datacloud_analysis.tools.file_io import read_file

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(
                os.environ,
                {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir},
            ),
        ):
            await asyncio.to_thread(
                Path(tmpdir, "data.txt").write_text,
                "fallback content",
                encoding="utf-8",
            )
            # 不传 _context，走降级路径
            result = await read_file.ainvoke({"path": "data.txt"})

        assert result == "fallback content"
