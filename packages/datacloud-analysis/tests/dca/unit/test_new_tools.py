"""Tests for new atomic tool files: ask_user, file_io, code_exec."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

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
        from datacloud_analysis.orchestration.execution.tool_wrapper import inject_reason_field

        # The schema should already have 'reason' as a field
        schema = ask_user.args_schema
        assert schema is not None
        assert "reason" in schema.model_fields


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

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await read_file.ainvoke({"path": "nonexistent.txt"})

        assert "错误" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_write_file_creates_file(self) -> None:
        from datacloud_analysis.tools.file_io import write_file

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await write_file.ainvoke({"path": "output.txt", "content": "data"})

            assert result["success"] is True
            assert Path(tmpdir, "output.txt").read_text() == "data"

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self) -> None:
        """Accessing files outside workspace_dir should return an error."""
        from datacloud_analysis.tools.file_io import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await read_file.ainvoke({"path": "../../etc/passwd"})

        assert "错误" in result or "error" in result.lower() or "outside" in result.lower()


# ---------------------------------------------------------------------------
# write_code / execute_code tools
# ---------------------------------------------------------------------------

class TestCodeExecTools:
    @pytest.mark.asyncio
    async def test_write_code_creates_py_file(self) -> None:
        from datacloud_analysis.tools.code_exec import write_code

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await write_code.ainvoke({"filename": "script.py", "code": "x = 1"})

        assert result["success"] is True
        assert result["path"].endswith(".py")

    @pytest.mark.asyncio
    async def test_write_code_adds_py_suffix(self) -> None:
        from datacloud_analysis.tools.code_exec import write_code

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await write_code.ainvoke({"filename": "myscript", "code": "pass"})

        assert result["success"] is True
        assert result["path"].endswith(".py")

    @pytest.mark.asyncio
    async def test_execute_code_runs_successfully(self) -> None:
        from datacloud_analysis.tools.code_exec import write_code, execute_code

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                await write_code.ainvoke({"filename": "calc.py", "code": "print('hello')\n_result = 42"})
                result = await execute_code.ainvoke({"filename": "calc.py"})

        assert result["exit_code"] == 0
        assert "hello" in result["output"]
        assert result["result"] == 42

    @pytest.mark.asyncio
    async def test_execute_code_missing_file(self) -> None:
        from datacloud_analysis.tools.code_exec import execute_code

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                result = await execute_code.ainvoke({"filename": "missing.py"})

        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_execute_code_syntax_error(self) -> None:
        from datacloud_analysis.tools.code_exec import write_code, execute_code

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                await write_code.ainvoke({"filename": "bad.py", "code": "def bad syntax"})
                result = await execute_code.ainvoke({"filename": "bad.py"})

        assert result["exit_code"] == 1
