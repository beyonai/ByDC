"""Tests for new atomic tool files: ask_user and file_io."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.file_storage import ResultFileStorage

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
            with InvocationContext(workspace_dir=tmpdir):
                result = await read_file.ainvoke({"path": "test.txt"})

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_missing_returns_error(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        with tempfile.TemporaryDirectory() as tmpdir, InvocationContext(workspace_dir=tmpdir):
            result = await read_file.ainvoke({"path": "nonexistent.txt"})

        assert "错误" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self) -> None:
        """Accessing files outside workspace_dir should return an error."""
        from datacloud_analysis.tools.file_io import read_file

        with tempfile.TemporaryDirectory() as tmpdir, InvocationContext(workspace_dir=tmpdir):
            result = await read_file.ainvoke({"path": "../../etc/passwd"})

        assert "错误" in result or "error" in result.lower() or "outside" in result.lower()


# ---------------------------------------------------------------------------
# ResultFileStorage 注入路径测试（InvocationContext.result_file_storage）
# ---------------------------------------------------------------------------


class TestFileIOToolsWithInjectedStorage:
    """验证 InvocationContext 注入 ResultFileStorage 时，工具走该后端而非本地磁盘。"""

    @pytest.mark.asyncio
    async def test_read_file_uses_injected_storage(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        mock_storage = MagicMock(spec=ResultFileStorage)
        mock_storage.read_text.return_value = "hello"

        with InvocationContext(result_file_storage=mock_storage):
            result = await read_file.ainvoke({"path": "/by/.sessions/u1/foo.txt"})

        assert result == "hello"
        mock_storage.read_text.assert_called_once_with(
            "/by/.sessions/u1/foo.txt", begin_line=0, end_line=-1
        )

    @pytest.mark.asyncio
    async def test_read_file_passes_line_range_to_storage(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        mock_storage = MagicMock(spec=ResultFileStorage)
        mock_storage.read_text.return_value = "line2\nline3"

        with InvocationContext(result_file_storage=mock_storage):
            result = await read_file.ainvoke({"path": "foo.txt", "begin_line": 1, "end_line": 3})

        assert result == "line2\nline3"
        mock_storage.read_text.assert_called_once_with("foo.txt", begin_line=1, end_line=3)

    @pytest.mark.asyncio
    async def test_read_file_returns_not_found_when_storage_returns_none(self) -> None:
        from datacloud_analysis.tools.file_io import read_file

        mock_storage = MagicMock(spec=ResultFileStorage)
        mock_storage.read_text.return_value = None

        with InvocationContext(result_file_storage=mock_storage):
            result = await read_file.ainvoke({"path": "missing.txt"})

        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_read_file_falls_back_to_local_when_storage_not_injected(self) -> None:
        """InvocationContext 未注入 result_file_storage 时，应降级到 LocalResultFileStorage。"""
        from datacloud_analysis.tools.file_io import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            await asyncio.to_thread(
                Path(tmpdir, "data.txt").write_text,
                "fallback content",
                encoding="utf-8",
            )
            with InvocationContext(workspace_dir=tmpdir):
                result = await read_file.ainvoke({"path": "data.txt"})

        assert result == "fallback content"
