"""read_file tool skill 路径分支单元测试。

覆盖验收用例：
  用例7  read_file 在 skill 上下文中读本地文件
  用例8  read_file 路径越权被拒绝
  用例9  非 skill 请求的 read_file 行为不变（走原有 storage 逻辑）
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_analysis.tools.file_io import read_file


def _make_skill_ctx(skill_workspace_dir: str) -> SimpleNamespace:
    return SimpleNamespace(
        user_id="0027024630",
        session_id="sess-001",
        extras={"skill_workspace_dir": skill_workspace_dir},
        result_file_storage=None,
        workspace_dir=None,
    )


def _make_non_skill_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        user_id="0027024630",
        session_id="sess-001",
        extras={},
        result_file_storage=None,
        workspace_dir=None,
    )


class TestReadFileSkillBranch:
    @pytest.mark.asyncio
    async def test_reads_local_file_in_skill_context(self, tmp_path: Path) -> None:
        """skill 上下文中直接读本地磁盘文件。"""
        target = tmp_path / "guide.md"
        target.write_text("skill content here", encoding="utf-8")

        ctx = _make_skill_ctx(str(tmp_path))
        with patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx):
            result = await read_file.ainvoke({"path": str(target)})

        assert result == "skill content here"

    @pytest.mark.asyncio
    async def test_relative_path_resolved_under_skill_dir(self, tmp_path: Path) -> None:
        """相对路径在 skill_workspace_dir 下解析。"""
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "run.py").write_text("print('hello')", encoding="utf-8")

        ctx = _make_skill_ctx(str(tmp_path))
        with patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx):
            result = await read_file.ainvoke({"path": "scripts/run.py"})

        assert "print('hello')" in result

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """路径越权（.. 穿越）被拒绝，返回错误信息。"""
        ctx = _make_skill_ctx(str(tmp_path))
        with patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx):
            result = await read_file.ainvoke({"path": "../../etc/passwd"})

        assert "错误" in result
        assert "超出" in result

    @pytest.mark.asyncio
    async def test_file_not_found_returns_error(self, tmp_path: Path) -> None:
        """文件不存在返回错误信息，不抛异常。"""
        ctx = _make_skill_ctx(str(tmp_path))
        with patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx):
            result = await read_file.ainvoke({"path": "nonexistent.md"})

        assert "错误" in result

    @pytest.mark.asyncio
    async def test_begin_end_line_slicing(self, tmp_path: Path) -> None:
        """begin_line / end_line 切片在 skill 路径下正常工作。"""
        target = tmp_path / "data.txt"
        target.write_text("line0\nline1\nline2\nline3", encoding="utf-8")

        ctx = _make_skill_ctx(str(tmp_path))
        with patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx):
            result = await read_file.ainvoke(
                {"path": str(target), "begin_line": 1, "end_line": 3}
            )

        assert "line1" in result
        assert "line2" in result
        assert "line0" not in result
        assert "line3" not in result

    @pytest.mark.asyncio
    async def test_non_skill_context_uses_storage(self) -> None:
        """非 skill 请求走原有 _resolve_storage() 逻辑，不读本地磁盘。"""
        mock_storage = MagicMock()
        mock_storage.read_text.return_value = "from storage"

        ctx = _make_non_skill_ctx()
        with (
            patch("datacloud_analysis.tools.file_io.get_current_context", return_value=ctx),
            patch("datacloud_analysis.tools.file_io._resolve_storage", return_value=mock_storage),
        ):
            result = await read_file.ainvoke({"path": "result.csv"})

        assert result == "from storage"
        mock_storage.read_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_context_uses_storage(self) -> None:
        """无 InvocationContext 时走原有 storage 逻辑，不抛异常。"""
        from datacloud_data_sdk.exceptions import DatacloudError

        mock_storage = MagicMock()
        mock_storage.read_text.return_value = "fallback content"

        with (
            patch(
                "datacloud_analysis.tools.file_io.get_current_context",
                side_effect=DatacloudError("no ctx"),
            ),
            patch("datacloud_analysis.tools.file_io._resolve_storage", return_value=mock_storage),
        ):
            result = await read_file.ainvoke({"path": "result.csv"})

        assert result == "fallback content"
