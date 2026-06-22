"""execute tool：在 skill 工作目录下执行 shell 命令。"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Annotated

# TODO(Phase 3): pass InvocationContext explicitly instead of global get_current_context
from datacloud_data_sdk.context import get_current_context
from datacloud_platform.errors import DatacloudError
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 120
_MAX_OUTPUT_BYTES = 100_000


@tool("execute")
async def execute(
    command: Annotated[str, "在 skill 工作目录下执行的 shell 命令"],
    timeout: Annotated[int, "超时秒数，默认 120"] = _DEFAULT_TIMEOUT,  # noqa: ASYNC109
) -> str:
    """在 skill 工作目录下执行 shell 命令，返回 stdout+stderr 合并输出。"""
    env = os.environ.copy()
    cwd = os.getcwd()

    try:
        ctx = get_current_context()
        extras = getattr(ctx, "extras", None) or {}
        if extras.get("user_code"):
            env["USER_CODE"] = str(extras["user_code"])
        if extras.get("beyond_token"):
            env["BEYOND_TOKEN"] = str(extras["beyond_token"])
        if extras.get("be_domainname"):
            env["BE_DOMAINNAME"] = str(extras["be_domainname"])
        skill_ws = str(extras.get("skill_workspace_dir") or "").strip()
        if skill_ws:
            cwd = skill_ws
            env["SKILL_WORKSPACE_DIR"] = skill_ws
        skill_dir = str(extras.get("skill_dir") or "").strip()
        if skill_dir:
            env["SKILL_DIR"] = skill_dir
    except DatacloudError:
        pass

    logger.info("execute: cwd=%s command=%r", cwd, command[:200])
    try:
        result = subprocess.run(  # noqa: ASYNC221
            command,
            shell=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"[超时] 命令执行超过 {timeout} 秒"
    except OSError as exc:
        return f"[错误] 命令执行失败：{exc}"

    output = result.stdout.rstrip()
    if result.stderr:
        stderr_lines = "\n".join(f"[stderr] {line}" for line in result.stderr.splitlines())
        output = f"{output}\n{stderr_lines}".strip() if output else stderr_lines

    if len(output.encode()) > _MAX_OUTPUT_BYTES:
        output = output.encode()[:_MAX_OUTPUT_BYTES].decode(errors="replace") + "\n[输出已截断]"

    if result.returncode != 0:
        output = (
            f"[exit={result.returncode}]\n{output}" if output else f"[exit={result.returncode}]"
        )

    return output or "(无输出)"
