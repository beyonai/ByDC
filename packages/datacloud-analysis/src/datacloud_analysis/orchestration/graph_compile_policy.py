"""Shared graph compile policy with mandatory checkpointer fail-fast."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_analysis.session.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


def compile_graph_with_policy(graph: Any, *, caller_name: str) -> Any:
    """Compile graph and require an initialized checkpointer.

    Policy:
    - checkpointer available -> compile(checkpointer=...)
    - checkpointer unavailable -> raise RuntimeError (fail-fast)
    """
    try:
        checkpointer = get_checkpointer()
    except RuntimeError as exc:
        raise RuntimeError(
            "Checkpointer is required but not initialized. "
            "Call `await bootstrap.setup()` before graph compilation."
        ) from exc

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("%s: compiled with PG checkpointer", caller_name)
    return compiled
