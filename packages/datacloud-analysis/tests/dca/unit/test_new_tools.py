"""Tests for new atomic tool files: ask_user, file_io, code_exec."""
from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Gateway file_manager 委托路径测试（_context 注入）
# ---------------------------------------------------------------------------

def _make_mock_context(
    read_return: dict | None = None,
    write_return: dict | None = None,
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


async def _invoke_with_context(tool_func, params: dict, ctx: MagicMock):
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

        ctx = _make_mock_context(
            read_return={"success": True, "data": {"content": "hello"}}
        )
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
            write_return={"success": True, "message": "ok", "data": {"path": "temp/out.txt", "bytes_written": 4}}
        )
        result = await _invoke_with_context(write_file, {"path": "temp/out.txt", "content": "data"}, ctx)

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

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "data.txt").write_text("fallback content", encoding="utf-8")
            with patch.dict(os.environ, {"DATACLOUD_ACTIVE_WORKSPACE": tmpdir}):
                # 不传 _context，走降级路径
                result = await read_file.ainvoke({"path": "data.txt"})

        assert result == "fallback content"


class TestCodeExecToolsWithGateway:
    """验收用例 5-6：write_code / execute_code 委托 Gateway FileManager。"""

    @pytest.mark.asyncio
    async def test_write_code_delegates_to_file_manager(self) -> None:
        """用例 5：write_code 委托 file_manager 写入 Python 文件，自动补 .py 后缀。"""
        from datacloud_analysis.tools.code_exec import write_code

        ctx = _make_mock_context(
            write_return={"success": True, "data": {"path": "analysis.py", "bytes_written": 12}}
        )
        result = await _invoke_with_context(write_code, {"filename": "analysis", "code": "print('ok')"}, ctx)

        assert result["success"] is True
        ctx.agent_runtime_state.session_manager.file_manager.write_file.assert_called_once_with(
            "analysis.py", "print('ok')"
        )

    @pytest.mark.asyncio
    async def test_execute_code_reads_via_file_manager_and_executes(self) -> None:
        """用例 6：execute_code 读文件走 file_manager，执行结果正确。"""
        from datacloud_analysis.tools.code_exec import execute_code

        ctx = _make_mock_context(
            read_return={"success": True, "data": {"content": "_result = {'count': 42}"}}
        )
        result = await _invoke_with_context(execute_code, {"filename": "analysis.py"}, ctx)

        assert result["exit_code"] == 0
        assert result["result"] == {"count": 42}
        ctx.agent_runtime_state.session_manager.file_manager.read_file.assert_called_once_with(
            "analysis.py"
        )

    @pytest.mark.asyncio
    async def test_execute_code_returns_error_when_file_manager_fails(self) -> None:
        """execute_code：file_manager 读取失败时返回 exit_code=1，不抛异常。"""
        from datacloud_analysis.tools.code_exec import execute_code

        ctx = _make_mock_context(
            read_return={"success": False, "error": "Permission denied"}
        )
        result = await _invoke_with_context(execute_code, {"filename": "analysis.py"}, ctx)

        assert result["exit_code"] == 1
        assert "Permission denied" in result["output"]
        assert result["result"] is None


class TestSandboxDeprecation:
    """验收用例 7：sbx_read_file 导入触发 DeprecationWarning。"""

    def test_sandbox_import_triggers_deprecation_warning(self) -> None:
        """用例 7：导入 sandbox 模块触发 DeprecationWarning。"""
        import sys
        # 确保模块未缓存，强制重新导入触发 warnings.warn
        sys.modules.pop("datacloud_analysis.tools.sandbox", None)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import datacloud_analysis.tools.sandbox  # noqa: F401

            assert any(
                issubclass(warning.category, DeprecationWarning)
                and "sandbox" in str(warning.message).lower()
                for warning in w
            ), f"Expected DeprecationWarning, got: {[str(x.message) for x in w]}"
