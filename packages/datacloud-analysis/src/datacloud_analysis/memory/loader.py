"""Long-term memory loader — passive global-rules injection (design §4.3.2.2 Track-1).

At task startup the Agent proactively fetches the user's ``global_rules``
(lightweight preferences, e.g. "always show amounts in 万元") and writes
them to ``./workspace/MEMORY.md`` inside the sandbox.

The main analysis process never blocks on memory collection; that is done
asynchronously by the Memory Worker after the task finishes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_MD_FILENAME = "MEMORY.md"


class MemoryLoader:
    """Fetch global rules and write MEMORY.md before the Agent starts reasoning.

    Args:
        user_id:     The current user.
        workspace:   Path to the Agent's sandbox workspace directory.
    """

    def __init__(self, user_id: str, workspace: Path) -> None:
        self._user_id = user_id
        self._workspace = workspace

    async def load(self) -> Path:
        """Fetch global_rules and write MEMORY.md.

        Returns:
            Path to the written MEMORY.md file.
        """
        rules = await self._fetch_global_rules()
        memory_path = self._workspace / _MEMORY_MD_FILENAME
        memory_path.write_text(self._render_markdown(rules), encoding="utf-8")
        logger.info("MemoryLoader: wrote %s (%d rules).", memory_path, len(rules))
        return memory_path

    async def _fetch_global_rules(self) -> list[dict[str, Any]]:
        """Pull lightweight global rules from datacloud-memory.

        TODO: replace stub with real call to ``datacloud_memory.query.get_global_rules()``.
        """
        try:
            from datacloud_memory.query import get_global_rules  # noqa: PLC0415

            raw_rules = await get_global_rules(self._user_id)
        except ImportError:
            logger.debug("datacloud-memory not available; skipping global rules.")
            return []

        if not isinstance(raw_rules, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_rules:
            if isinstance(item, dict):
                normalized.append(dict(item))
        return normalized

    @staticmethod
    def _render_markdown(rules: list[dict[str, Any]]) -> str:
        if not rules:
            return "# Memory\n\n_No global rules configured._\n"
        lines = ["# Memory\n", "## Global Rules\n"]
        for rule in rules:
            title = rule.get("title", "rule")
            content = rule.get("content", "")
            lines.append(f"### {title}\n{content}\n")
        return "\n".join(lines)
