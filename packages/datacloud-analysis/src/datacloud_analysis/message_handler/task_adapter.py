"""Task scheduler client — pull tasks and push results (design §调度层).

The task scheduler is a **third-party service**.  This module is the only
place that talks to it.  It contains *only* client-side logic:
- poll / subscribe for new tasks
- acknowledge or reject a task
- post the final result (with optional attachment IDs) back
- emit async events (HITL interruption, memory collection signal)

All method bodies are stubs (``raise NotImplementedError``) and must be
filled in once the task scheduler API contract is known.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_analysis.config.models import TaskContext, TaskResult

logger = logging.getLogger(__name__)


class TaskSchedulerClient:
    """HTTP / message-queue client for the external task scheduler.

    Args:
        base_url:  Base URL of the task scheduler API.
        api_key:   Authentication key (injected from env via ``Settings``).
        agent_id:  The identifier this Agent registers as with the scheduler.
    """

    def __init__(self, base_url: str, api_key: str, agent_id: str) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._agent_id = agent_id

    async def poll_next_task(self) -> TaskContext | None:
        """Fetch the next pending task from the scheduler queue.

        Returns:
            A ``TaskContext`` if a task is available, else ``None``.
        """
        raise NotImplementedError

    async def acknowledge_task(self, task_id: str) -> None:
        """Acknowledge that the Agent has accepted a task (prevents re-delivery)."""
        raise NotImplementedError

    async def submit_result(self, result: TaskResult) -> None:
        """Post the completed task result back to the scheduler.

        Args:
            result: The ``TaskResult`` produced by the Agent.
        """
        raise NotImplementedError

    async def emit_hitl_event(
        self,
        task_id: str,
        thread_id: str,
        checkpoint_id: str,
        interaction_payload: dict[str, Any],
    ) -> None:
        """Notify the scheduler that the Agent requires human input.

        The scheduler will forward ``interaction_payload`` to the frontend
        as an interactive card.  When the user responds, the scheduler will
        call the Agent's resume endpoint with the same ``thread_id`` and
        ``checkpoint_id``.

        Args:
            task_id:              The paused task.
            thread_id:            LangGraph thread for snapshot lookup.
            checkpoint_id:        The checkpoint frozen at interrupt time.
            interaction_payload:  UI card data (question, options, etc.).
        """
        raise NotImplementedError

    async def emit_memory_collection_event(
        self, task_id: str, thread_id: str, user_id: str
    ) -> None:
        """Signal that a task has completed and memory distillation should start.

        The scheduler routes this to the async Memory Worker
        (``datacloud_memory.build``).
        """
        raise NotImplementedError
