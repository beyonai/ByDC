from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_sbx_write_then_read_roundtrip() -> None:
    from datacloud_analysis.tools.sandbox import sbx_read_file, sbx_write_file

    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"DATACLOUD_SANDBOX_ROOT": tmpdir}
        with patch.dict(os.environ, env):
            written_path = await sbx_write_file.ainvoke(
                {"path": "outputs/result.txt", "content": "hello", "task_id": "task-1"}
            )
            content = await sbx_read_file.ainvoke({"path": "outputs/result.txt", "task_id": "task-1"})
            disk_content = await asyncio.to_thread(Path(written_path).read_text, encoding="utf-8")
            assert disk_content == "hello"
            assert content == "hello"


@pytest.mark.asyncio
async def test_sbx_write_rejects_parent_traversal() -> None:
    from datacloud_analysis.tools.sandbox import sbx_write_file

    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"DATACLOUD_SANDBOX_ROOT": tmpdir}
        with patch.dict(os.environ, env), pytest.raises(ValueError, match="outside sandbox"):
            await sbx_write_file.ainvoke({"path": "../escape.txt", "content": "x", "task_id": "task-1"})
