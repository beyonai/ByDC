"""Session management package (design §4.1).

Sub-modules
-----------
checkpointer   Singleton accessor for the LangGraph checkpointer (bootstrap path).
pg_opengauss   OpenGauss-compatible checkpointer + langgraph dev factory.
metadata       Map business IDs (session_id, message_id) to LangGraph thread_id.
"""

from .checkpointer import get_checkpointer, reset_checkpointer, set_checkpointer
from .metadata import SessionMetadata, build_run_config
from .pg_opengauss import (
    OpenGaussSaver,
    SyncPGCheckpointer,
    make_opengauss_saver,
    ensure_tables_opengauss,
    get_checkpointer as get_opengauss_checkpointer,
)

__all__ = [
    # bootstrap-path singleton
    "get_checkpointer",
    "reset_checkpointer",
    "set_checkpointer",
    # session metadata
    "SessionMetadata",
    "build_run_config",
    # OpenGauss / langgraph-dev path
    "OpenGaussSaver",
    "SyncPGCheckpointer",
    "make_opengauss_saver",
    "ensure_tables_opengauss",
    "get_opengauss_checkpointer",
]
