"""Business ID → LangGraph thread_id mapping (design §4.1.3.1).

Design reference
----------------
``checkpoints.metadata`` stores the mapping from the Agent's internal
``thread_id`` back to the business identifiers (``session_id``,
``message_id``, ``attachment_ids``).  This makes it possible for the
task scheduler to later look up which thread was handling a given message.

``build_run_config`` constructs the ``{"configurable": {"thread_id": …}}``
dict expected by LangGraph, and injects business metadata so it is
persisted with every checkpoint.
"""

from __future__ import annotations

import uuid
from typing import Any


class SessionMetadata:
    """Immutable bundle of IDs for one Agent run.

    Attributes
    ----------
    thread_id:      LangGraph thread ID (auto-generated; owned by the Agent).
    message_id:     Business message ID from the task scheduler.
    session_id:     Business session ID from the calling application.
    user_id:        User who triggered this task.
    attachment_ids: Uploaded file IDs attached to this message.
    """

    __slots__ = ("thread_id", "message_id", "session_id", "user_id", "attachment_ids")

    def __init__(
        self,
        *,
        message_id: str,
        session_id: str,
        user_id: str,
        attachment_ids: list[str] | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.thread_id = thread_id or _new_thread_id()
        self.message_id = message_id
        self.session_id = session_id
        self.user_id = user_id
        self.attachment_ids = attachment_ids or []

    def to_checkpoint_metadata(self) -> dict[str, Any]:
        """Return the dict that will be written into ``checkpoints.metadata``.

        This is the "source-of-truth" linkage between the LangGraph thread
        and the business session (design §4.1.3.1).
        """
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "attachment_ids": self.attachment_ids,
        }


def build_run_config(meta: SessionMetadata) -> dict[str, Any]:
    """Build the LangGraph ``config`` dict for ``graph.astream`` / ``ainvoke``.

    Args:
        meta: The session metadata for the current run.

    Returns:
        ``{"configurable": {"thread_id": "…"}}`` with metadata embedded.
    """
    return {
        "configurable": {
            "thread_id": meta.thread_id,
            # LangGraph stores any extra keys in configurable as checkpoint metadata.
            "metadata": meta.to_checkpoint_metadata(),
        }
    }


def _new_thread_id() -> str:
    return f"thread-{uuid.uuid4().hex}"
