"""Event types for OpenClaw Gateway."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """Event types for the OpenClaw Gateway."""

    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TOOL_CALL_ERROR = "tool_call_error"
    TURN_START = "turn_start"
    TURN_COMPLETE = "turn_complete"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    QUEUE_ADD = "queue_add"
    QUEUE_REMOVE = "queue_remove"


@dataclass
class Event:
    """Event dataclass for the OpenClaw Gateway.

    Attributes:
        type: The type of event
        data: Event data as a dictionary
        timestamp: Event timestamp
        session_id: Session identifier
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not isinstance(self.type, EventType):
            raise TypeError(f"type must be EventType, got {type(self.type)}")
        if not isinstance(self.data, dict):
            raise TypeError(f"data must be dict, got {type(self.data)}")
        if not isinstance(self.timestamp, datetime):
            raise TypeError(f"timestamp must be datetime, got {type(self.timestamp)}")
