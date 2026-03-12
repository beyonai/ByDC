"""Session management package (design §4.1).

Sub-modules
-----------
checkpointer   Wrap LangGraph AsyncPostgresSaver; expose a singleton getter.
metadata       Map business IDs (session_id, message_id) to LangGraph thread_id.
"""

from .checkpointer import get_checkpointer
from .metadata import SessionMetadata, build_run_config

__all__ = ["get_checkpointer", "SessionMetadata", "build_run_config"]
