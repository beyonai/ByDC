"""LangGraph PostgreSQL checkpointer wrapper (design §4.1.3.2).

The ``AsyncPostgresSaver`` is *not* created here — that happens once in
``bootstrap.setup()``.  This module only provides a thin accessor so that
the orchestration layer can retrieve the ready-to-use saver without knowing
about bootstrapping details.

Usage in orchestration::

    from datacloud_analysis.session.checkpointer import get_checkpointer

    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_checkpointer: "AsyncPostgresSaver | None" = None


def set_checkpointer(saver: "AsyncPostgresSaver") -> None:
    """Register the checkpointer instance (called once by bootstrap)."""
    global _checkpointer
    _checkpointer = saver


def get_checkpointer() -> "AsyncPostgresSaver":
    """Return the initialized checkpointer.

    Raises
    ------
    RuntimeError
        If ``bootstrap.setup()`` has not been called yet.
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer is not initialized. "
            "Call `await bootstrap.setup()` first."
        )
    return _checkpointer
