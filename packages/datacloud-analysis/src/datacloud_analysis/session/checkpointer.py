"""LangGraph PostgreSQL checkpointer wrapper (design §4.1.3.2).

``bootstrap.setup()`` opens the PG-backed saver (OpenGauss-compatible
``SyncPGCheckpointer`` from ``pg_opengauss``) and registers it via
``set_checkpointer``.  Callers use ``get_checkpointer()`` when compiling graphs.

Usage in orchestration::

    from datacloud_analysis.session.checkpointer import get_checkpointer

    checkpointer = get_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

_checkpointer: BaseCheckpointSaver[Any] | None = None


def set_checkpointer(saver: BaseCheckpointSaver[Any]) -> None:
    """Register the checkpointer instance (called once by ``bootstrap.setup()``)."""

    global _checkpointer
    _checkpointer = saver


def reset_checkpointer() -> None:
    """Clear the registered checkpointer (e.g. ``bootstrap.teardown()``)."""

    global _checkpointer
    _checkpointer = None


def get_checkpointer() -> BaseCheckpointSaver[Any]:
    """Return the initialized checkpointer.

    Raises
    ------
    RuntimeError
        If ``bootstrap.setup()`` has not registered a checkpointer yet.
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer is not initialized. "
            "Call `await bootstrap.setup()` first."
        )
    return _checkpointer
