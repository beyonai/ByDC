"""Queue policy for action resolution."""

from enum import Enum
from datacloud_agent.queue.types import QueueMode


class QueueAction(str, Enum):
    """Action to take for a message based on policy."""

    EXECUTE = "execute"  # Run immediately
    ENQUEUE = "enqueue"  # Add to queue
    ENQUEUE_FOLLOWUP = "enqueue-followup"  # Add as followup
    STEER = "steer"  # Interrupt and steer
    INTERRUPT = "interrupt"  # Cancel active run
    DROP = "drop"  # Drop message


class QueuePolicy:
    """Policy for resolving queue actions based on state and mode."""

    @staticmethod
    def resolve(
        is_active: bool,
        is_heartbeat: bool,
        should_followup: bool,
        queue_mode: QueueMode,
    ) -> QueueAction:
        """Resolve the action to take for a message.

        Args:
            is_active: Whether there is an active run for the session.
            is_heartbeat: Whether this is a heartbeat message (keep-alive).
            should_followup: Whether this message is a followup to previous.
            queue_mode: The queue mode requested.

        Returns:
            QueueAction to take.
        """
        # Heartbeat messages are always dropped (no effect)
        if is_heartbeat:
            return QueueAction.DROP

        # If no active run, execute immediately regardless of mode
        if not is_active:
            return QueueAction.EXECUTE

        # Active session: decide based on queue mode
        if queue_mode == QueueMode.COLLECT:
            return QueueAction.ENQUEUE
        elif queue_mode == QueueMode.FOLLOWUP:
            return QueueAction.ENQUEUE_FOLLOWUP
        elif queue_mode == QueueMode.STEER:
            return QueueAction.STEER
        elif queue_mode == QueueMode.STEER_BACKLOG:
            # Steer requests go to backlog (treated as regular enqueue)
            return QueueAction.ENQUEUE
        elif queue_mode == QueueMode.INTERRUPT:
            return QueueAction.INTERRUPT
        elif queue_mode == QueueMode.QUEUE:
            # Default queue behavior (enqueue)
            return QueueAction.ENQUEUE
        else:
            # Unknown mode, default to enqueue
            return QueueAction.ENQUEUE
