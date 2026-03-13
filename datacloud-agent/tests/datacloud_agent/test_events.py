"""Tests for the events module."""

from datetime import datetime

import pytest

from datacloud_agent.events import EventEmitter, Event, EventType


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that all expected event types exist."""
        expected_types = [
            "message_received",
            "message_sent",
            "agent_start",
            "agent_complete",
            "agent_error",
            "error",
            "warning",
            "info",
            "tool_call_start",
            "tool_call_complete",
            "tool_call_error",
            "turn_start",
            "turn_complete",
            "session_start",
            "session_end",
            "queue_add",
            "queue_remove",
        ]
        actual_values = [e.value for e in EventType]
        for expected in expected_types:
            assert expected in actual_values


class TestEvent:
    """Tests for Event dataclass."""

    def test_create_event(self):
        """Test basic event creation."""
        event = Event(type=EventType.MESSAGE_RECEIVED, data={"msg": "hello"})
        assert event.type == EventType.MESSAGE_RECEIVED
        assert event.data == {"msg": "hello"}
        assert isinstance(event.timestamp, datetime)
        assert event.session_id == ""

    def test_create_event_with_session_id(self):
        """Test event creation with session_id."""
        event = Event(
            type=EventType.AGENT_START,
            data={"agent": "main"},
            session_id="session-123",
        )
        assert event.session_id == "session-123"

    def test_event_validation_invalid_type(self):
        """Test that invalid type raises TypeError."""
        with pytest.raises(TypeError):
            Event(type="message_received", data={})

    def test_event_validation_invalid_data(self):
        """Test that invalid data raises TypeError."""
        with pytest.raises(TypeError):
            Event(type=EventType.MESSAGE_RECEIVED, data="not a dict")

    def test_event_default_timestamp(self):
        """Test that timestamp defaults to now."""
        before = datetime.now()
        event = Event(type=EventType.INFO, data={})
        after = datetime.now()
        assert before <= event.timestamp <= after


class TestEventEmitter:
    """Tests for EventEmitter class."""

    def test_create_emitter(self):
        """Test creating an emitter."""
        emitter = EventEmitter()
        assert emitter.history_size == 100

    def test_create_emitter_with_custom_history_size(self):
        """Test creating an emitter with custom history size."""
        emitter = EventEmitter(history_size=50)
        assert emitter.history_size == 50

    def test_on_event_register_handler(self):
        """Test registering an event handler."""
        emitter = EventEmitter()
        received = []

        def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        assert len(emitter._handlers[EventType.MESSAGE_RECEIVED]) == 1

    def test_off_event_unregister_handler(self):
        """Test unregistering an event handler."""
        emitter = EventEmitter()
        received = []

        def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        emitter.off_event(EventType.MESSAGE_RECEIVED, handler)
        assert EventType.MESSAGE_RECEIVED not in emitter._handlers

    def test_off_event_handler_not_found(self):
        """Test that off_event doesn't raise if handler not found."""
        emitter = EventEmitter()

        def handler(event):
            pass

        # Should not raise
        emitter.off_event(EventType.MESSAGE_RECEIVED, handler)

    @pytest.mark.asyncio
    async def test_emit_async_handler(self):
        """Test emitting an event to an async handler."""
        emitter = EventEmitter()
        received = []

        async def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={"msg": "hello"}))

        assert len(received) == 1
        assert received[0].data == {"msg": "hello"}

    @pytest.mark.asyncio
    async def test_emit_sync_handler(self):
        """Test emitting an event to a sync handler."""
        emitter = EventEmitter()
        received = []

        def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={"msg": "hello"}))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_multiple_handlers(self):
        """Test emitting to multiple handlers."""
        emitter = EventEmitter()
        received1 = []
        received2 = []

        def handler1(event):
            received1.append(event)

        async def handler2(event):
            received2.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler1)
        emitter.on_event(EventType.MESSAGE_RECEIVED, handler2)
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={}))

        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self):
        """Test emitting with no handlers registered."""
        emitter = EventEmitter()
        # Should not raise
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={}))

    def test_emit_sync(self):
        """Test synchronous emit."""
        emitter = EventEmitter()
        received = []

        def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        emitter.emit_sync(Event(type=EventType.MESSAGE_RECEIVED, data={}))

        assert len(received) == 1

    def test_get_history(self):
        """Test getting event history."""
        emitter = EventEmitter()
        emitter.emit_sync(Event(type=EventType.MESSAGE_RECEIVED, data={}))
        emitter.emit_sync(Event(type=EventType.MESSAGE_SENT, data={}))

        history = emitter.get_history()
        assert len(history) == 2
        # Most recent first
        assert history[0].type == EventType.MESSAGE_SENT
        assert history[1].type == EventType.MESSAGE_RECEIVED

    def test_get_history_with_type_filter(self):
        """Test filtering history by event type."""
        emitter = EventEmitter()
        emitter.emit_sync(Event(type=EventType.MESSAGE_RECEIVED, data={}))
        emitter.emit_sync(Event(type=EventType.MESSAGE_SENT, data={}))
        emitter.emit_sync(Event(type=EventType.MESSAGE_RECEIVED, data={}))

        history = emitter.get_history(event_type=EventType.MESSAGE_RECEIVED)
        assert len(history) == 2
        assert all(e.type == EventType.MESSAGE_RECEIVED for e in history)

    def test_get_history_with_limit(self):
        """Test limiting history results."""
        emitter = EventEmitter(history_size=10)
        for i in range(20):
            emitter.emit_sync(Event(type=EventType.INFO, data={"i": i}))

        history = emitter.get_history(limit=5)
        assert len(history) == 5

    def test_clear_history(self):
        """Test clearing event history."""
        emitter = EventEmitter()
        emitter.emit_sync(Event(type=EventType.MESSAGE_RECEIVED, data={}))
        emitter.clear_history()

        history = emitter.get_history()
        assert len(history) == 0

    def test_circular_buffer(self):
        """Test that history respects maxlen (circular buffer)."""
        emitter = EventEmitter(history_size=3)
        for i in range(5):
            emitter.emit_sync(Event(type=EventType.INFO, data={"i": i}))

        history = emitter.get_history()
        # Should only have 3 most recent
        assert len(history) == 3
        # Should have events 2, 3, 4 (0-indexed)
        assert history[0].data["i"] == 4
        assert history[1].data["i"] == 3
        assert history[2].data["i"] == 2


class TestEventEmitterIntegration:
    """Integration tests for EventEmitter."""

    @pytest.mark.asyncio
    async def test_qa_scenario_1(self):
        """Test QA scenario 1: Register and emit event."""
        emitter = EventEmitter()
        received = []

        async def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={"msg": "hello"}))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_qa_scenario_2(self):
        """Test QA scenario 2: Event history."""
        emitter = EventEmitter()
        received = []

        async def handler(event):
            received.append(event)

        emitter.on_event(EventType.MESSAGE_RECEIVED, handler)
        await emitter.emit(Event(type=EventType.MESSAGE_RECEIVED, data={"msg": "hello"}))

        history = emitter.get_history()
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_agent_lifecycle_events(self):
        """Test typical agent lifecycle: start -> complete."""
        emitter = EventEmitter()
        events = []

        def track(event):
            events.append(event)

        emitter.on_event(EventType.AGENT_START, track)
        emitter.on_event(EventType.AGENT_COMPLETE, track)
        emitter.on_event(EventType.ERROR, track)

        # Agent starts
        await emitter.emit(
            Event(
                type=EventType.AGENT_START,
                data={"agent": "main"},
                session_id="session-1",
            )
        )

        # Agent completes
        await emitter.emit(
            Event(
                type=EventType.AGENT_COMPLETE,
                data={"result": "success"},
                session_id="session-1",
            )
        )

        assert len(events) == 2
        assert events[0].type == EventType.AGENT_START
        assert events[1].type == EventType.AGENT_COMPLETE

        # Check history
        history = emitter.get_history()
        assert len(history) == 2
