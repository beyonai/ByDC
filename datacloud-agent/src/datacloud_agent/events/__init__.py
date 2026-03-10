"""Event system for OpenClaw Gateway.

This module provides event types and an event emitter for the OpenClaw Gateway.
"""

from datacloud_agent.events.emitter import EventEmitter
from datacloud_agent.events.types import Event, EventType

__all__ = ["EventEmitter", "Event", "EventType"]
