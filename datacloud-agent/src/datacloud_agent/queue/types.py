"""Queue types for OpenClaw Gateway."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class QueueMode(str, Enum):
    """Queue mode for message handling."""

    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"
    STEER_BACKLOG = "steer_backlog"
    INTERRUPT = "interrupt"
    QUEUE = "queue"


class DropPolicy(str, Enum):
    """Policy for handling queue overflow."""

    OLD = "old"  # Drop oldest messages
    NEW = "new"  # Drop new messages (reject)
    SUMMARIZE = "summarize"  # Summarize old messages


@dataclass
class QueueSettings:
    """Settings for queue behavior."""

    mode: QueueMode = QueueMode.COLLECT
    max_size: int = 100
    drop_policy: DropPolicy = DropPolicy.NEW
    ttl_seconds: int | None = None


@dataclass
class QueuedMessage:
    """A message in the queue."""

    prompt: str
    session_key: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class QueueState:
    """State of a queue for a session."""

    session_key: str
    messages: list[QueuedMessage] = field(default_factory=list)
    mode: QueueMode = QueueMode.COLLECT
    max_size: int = 100
    drop_policy: DropPolicy = DropPolicy.NEW
    is_processing: bool = False
    last_activity: datetime = field(default_factory=datetime.now)
