"""execute tool 单元测试。

覆盖验收用例：
  用例6  多用户并发变量不串台（USER_CODE/BEYOND_TOKEN 从 extras 注入子进程 env）
  用例A  正常命令执行返回 stdout
  用例B  命令超时返回超时提示
  用例C  非零退出码在输出中标注
  用例D  stderr 合并到输出
  用例E  无 InvocationContext 时降级到 os.getcwd()
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datacloud_analysis.tools.execute import execute


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：构造 InvocationContext mock
# ─────────────────────────────────────────────────────────────────────────────


def _make_ctx(
    user_code: str = "0027024630",
    beyond_token: str = "token-abc",
    skill_workspace_dir: str = "/tmp/skill_ws",
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_code,
        session_id="sess-001",
        extras={
            "user_code": user_code,
            "beyond_token": beyond_token,
            "skill_workspace_dir": skill_workspace_dir,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_stdout_returned(self, tmp_path) -> None:
        """正常命令的 stdout 被返回。"""
        ctx = _make_ctx(skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke({"command": "echo hello"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_user_code_injected_into_subprocess_env(self, tmp_path) -> None:
        """USER_CODE 从 extras 注入子进程 env，不使用进程级环境变量。"""
        ctx = _make_ctx(user_code="USER_A", skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke(
                {"command": "python -c \"import os; print(os.environ.get('USER_CODE', ''))\""}
            )
        assert "USER_A" in result

    @pytest.mark.asyncio
    async def test_beyond_token_injected_into_subprocess_env(self, tmp_path) -> None:
        """BEYOND_TOKEN 从 extras 注入子进程 env。"""
        ctx = _make_ctx(beyond_token="TOKEN_XYZ", skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke(
                {"command": "python -c \"import os; print(os.environ.get('BEYOND_TOKEN', ''))\""}
            )
        assert "TOKEN_XYZ" in result

    @pytest.mark.asyncio
    async def test_concurrent_users_env_isolated(self, tmp_path) -> None:
        """不同用户的 USER_CODE 各自注入子进程 env，互不干扰。

        注：patch 是线程级的，无法在同一线程内同时 patch 两个不同值。
        此处顺序验证两次调用各自拿到正确的 USER_CODE，
        真正的并发隔离由 subprocess.run 的独立子进程保证（每次调用都复制当时的 env）。
        """
        cmd = "python -c \"import os; print(os.environ.get('USER_CODE', ''))\""

        ctx_a = _make_ctx(user_code="USER_A", skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx_a):
            result_a = await execute.ainvoke({"command": cmd})

        ctx_b = _make_ctx(user_code="USER_B", skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx_b):
            result_b = await execute.ainvoke({"command": cmd})

        assert "USER_A" in result_a
        assert "USER_B" in result_b
        assert "USER_B" not in result_a
        assert "USER_A" not in result_b

    @pytest.mark.asyncio
    async def test_nonzero_exit_code_annotated(self, tmp_path) -> None:
        """非零退出码在输出中标注 [exit=N]。"""
        ctx = _make_ctx(skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke({"command": "exit 1"})
        assert "[exit=1]" in result

    @pytest.mark.asyncio
    async def test_timeout_returns_message(self, tmp_path) -> None:
        """命令超时返回超时提示，不抛异常。"""
        ctx = _make_ctx(skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke(
                {"command": "python -c \"import time; time.sleep(10)\"", "timeout": 1}
            )
        assert "超时" in result

    @pytest.mark.asyncio
    async def test_stderr_merged_into_output(self, tmp_path) -> None:
        """stderr 合并到输出，前缀 [stderr]。"""
        ctx = _make_ctx(skill_workspace_dir=str(tmp_path))
        with patch("datacloud_analysis.tools.execute.get_current_context", return_value=ctx):
            result = await execute.ainvoke(
                {"command": "python -c \"import sys; sys.stderr.write('err_msg\\n')\""}
            )
        assert "[stderr]" in result
        assert "err_msg" in result

    @pytest.mark.asyncio
    async def test_no_context_falls_back_gracefully(self) -> None:
        """无 InvocationContext 时不抛异常，降级到 os.getcwd()。"""
        from datacloud_data_sdk.exceptions import DatacloudError

        with patch(
            "datacloud_analysis.tools.execute.get_current_context",
            side_effect=DatacloudError("no ctx"),
        ):
            result = await execute.ainvoke({"command": "echo fallback"})
        assert "fallback" in result
