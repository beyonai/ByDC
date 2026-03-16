"""T_REPORT — render_report: assemble the final data output protocol (design §3.1).

Collects charts, tables, text and trace evidence from the completed
sub-tasks and packages them into the ``a2Ui`` payload that the task
scheduler will forward to the frontend renderer.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def render_report(
    title: str,
    sections: list[dict[str, Any]],
    trace_refs: list[str] | None = None,
    attachment_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the final ``a2Ui`` visualisation payload.

    Args:
        title:            Report title.
        sections:         List of section dicts, each with a ``type`` key:
                          ``{"type": "text", "content": "…"}``
                          ``{"type": "table", "columns": […], "rows": […]}``
                          ``{"type": "chart", "chart_type": "bar", "data": {…}}``
        trace_refs:       Source evidence references (SQL queries, data slice IDs).
        attachment_paths: Paths of output files to be uploaded and referenced.

    Returns:
        The ``a2Ui`` report protocol dict ready for the task scheduler callback.
    """
    report: dict[str, Any] = {
        "title": title,
        "sections": sections,
        "trace_refs": trace_refs or [],
        "attachments": [],
    }

    # Upload output files and collect their attachment IDs.
    for path in attachment_paths or []:
        # TODO: call task scheduler client to upload file and get attachment_id.
        logger.debug("render_report: would upload %s", path)
        report["attachments"].append({"path": path, "attachment_id": None})

    logger.info("render_report: assembled report with %d sections.", len(sections))
    return report
