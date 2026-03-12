"""Message handler — Agent gateway entry point (design §3.1 AGENT_GATEWAY).

Responsibilities (per design flowchart)
----------------------------------------
1. Receive the raw task payload from the task scheduler.
2. Rewrite / clarify the business question (optional pre-processing step).
3. Initialise workspace directories and session metadata.
4. Dispatch to the orchestration layer (``orchestration.intent``).
5. On HITL interrupt: persist snapshot and emit a callback event.
6. On RESUME: load the checkpoint by thread_id and re-enter the loop.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from datacloud_agent.config.models import TaskContext, TaskResult
from datacloud_agent.session.metadata import SessionMetadata, build_run_config
from datacloud_agent.workspace.mount import SandboxMounter
from datacloud_agent.workspace.paths import build_task_paths

logger = logging.getLogger(__name__)


class MessageHandler:
    """Process one inbound task message end-to-end.

    Instantiate once per task.  Call ``handle()`` to run the full flow.
    """

    def __init__(self, context: TaskContext) -> None:
        self._ctx = context
        self._meta = SessionMetadata(
            message_id=context.message_id,
            session_id=context.session_id,
            user_id=context.user_id,
            attachment_ids=context.attachment_ids,
            thread_id=context.thread_id,
        )

    async def handle(self, user_message: str) -> AsyncIterator[dict[str, Any]]:
        """Run the Agent for the given message and yield streaming events.

        Args:
            user_message: The (possibly already rewritten) user question.

        Yields:
            LangGraph stream events (type, data).
        """
        logger.info(
            "MessageHandler.handle: task=%s thread=%s",
            self._ctx.task_id,
            self._meta.thread_id,
        )

        # Prepare workspace directories.
        task_paths = build_task_paths(self._ctx.user_id, self._ctx.task_id)
        mounter = SandboxMounter(task_paths)
        mounter.prepare()

        # Stage any attachments into inputs/.
        # TODO: download attachments via task scheduler client and stage them.

        # Build the LangGraph run config (thread_id + metadata).
        run_config = build_run_config(self._meta)

        # Delegate to orchestration (import lazily to avoid circular imports).
        from datacloud_agent.orchestration.intent import run_agent  # noqa: PLC0415

        async for event in run_agent(
            user_message=user_message,
            task_paths=task_paths,
            run_config=run_config,
        ):
            yield event

    async def resume(
        self,
        resume_value: Any,
        checkpoint_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume an interrupted (HITL) execution.

        Args:
            resume_value:  User's response to the interruption card.
            checkpoint_id: The ``checkpoint_id`` saved when the Agent paused.

        Yields:
            LangGraph stream events continuing from the checkpoint.
        """
        from langgraph.types import Command  # noqa: PLC0415

        run_config = build_run_config(self._meta)
        run_config["configurable"]["checkpoint_id"] = checkpoint_id

        from datacloud_agent.orchestration.intent import run_agent  # noqa: PLC0415

        async for event in run_agent(
            user_message=Command(resume=resume_value),
            task_paths=build_task_paths(self._ctx.user_id, self._ctx.task_id),
            run_config=run_config,
        ):
            yield event

    @staticmethod
    def _rewrite_question(raw: str) -> str:
        """Optional pre-processing: normalise or clarify the raw user question.

        Currently a pass-through; expand with a fast LLM call when needed.
        """
        return raw
