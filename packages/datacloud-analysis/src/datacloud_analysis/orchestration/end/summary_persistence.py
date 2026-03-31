"""Execution summary persistence interface (G16 contract)."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, TypedDict

from datacloud_analysis.orchestration.end.execution_summary import ExecutionSummary


class ExecutionSummaryPersistRef(TypedDict, total=False):
    """Persistence result envelope for execution summary."""

    status: str
    storage: str
    summary_id: str
    error: str


class ExecutionSummaryStore(Protocol):
    """Persistence interface for execution summary."""

    async def persist(self, summary: ExecutionSummary) -> ExecutionSummaryPersistRef:
        """Persist summary and return reference metadata."""


class NoopExecutionSummaryStore:
    """Default no-op store (actual persistence in G17)."""

    async def persist(self, summary: ExecutionSummary) -> ExecutionSummaryPersistRef:
        _ = summary
        return {"status": "skipped", "storage": "noop"}


@lru_cache(maxsize=1)
def get_execution_summary_store() -> ExecutionSummaryStore:
    """Return process-level summary persistence implementation."""
    return NoopExecutionSummaryStore()


