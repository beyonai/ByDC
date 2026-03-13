"""Sandbox tools — T_SBX_RUN / T_SBX_READ / T_SBX_WRITE (design §3.1 / §4.4).

These three tools are the Agent's hands inside the isolated sandbox
(LocalDockerBackend or RemoteDockerBackend).  They map directly to the
three sandbox symbols in the design flowchart.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def sbx_run_code(
    code: str,
    language: str = "python",
    timeout: int = 120,
    task_id: str = "",
) -> dict[str, Any]:
    """T_SBX_RUN — execute code inside the isolated sandbox container.

    Args:
        code:     Source code to run (Python or Bash).
        language: ``"python"`` or ``"bash"``.
        timeout:  Execution timeout in seconds.
        task_id:  Used to route to the correct sandbox instance.

    Returns:
        ``{"exit_code": int, "output": str, "truncated": bool}``
    """
    # TODO: resolve sandbox backend from task_id and call backend.execute(cmd).
    raise NotImplementedError(
        "sbx_run_code: sandbox backend integration not yet implemented."
    )


@tool
async def sbx_read_file(path: str, task_id: str = "") -> str:
    """T_SBX_READ — read a file from the sandbox workspace.

    Args:
        path:    Relative path inside the sandbox (e.g. ``outputs/report.csv``).
        task_id: Used to locate the correct sandbox instance.

    Returns:
        File contents as a string (binary files base64-encoded).
    """
    raise NotImplementedError(
        "sbx_read_file: sandbox backend integration not yet implemented."
    )


@tool
async def sbx_write_file(path: str, content: str, task_id: str = "") -> str:
    """T_SBX_WRITE — write or overwrite a file in the sandbox workspace.

    Args:
        path:    Relative path inside the sandbox.
        content: Text content to write.
        task_id: Used to locate the correct sandbox instance.

    Returns:
        Absolute path of the written file inside the sandbox.
    """
    raise NotImplementedError(
        "sbx_write_file: sandbox backend integration not yet implemented."
    )
