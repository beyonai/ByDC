"""Tests for queue types and manager."""

import pytest

from datacloud_agent.queue import (
    QueueManager,
    QueueMode,
    DropPolicy,
    QueueSettings,
    QueuedMessage,
    QueueState,
)


class TestQueueMode:
    """Tests for QueueMode enum."""

    def test_queue_mode_values(self):
        """Test all QueueMode values."""
        assert QueueMode.STEER.value == "steer"
        assert QueueMode.FOLLOWUP.value == "followup"
        assert QueueMode.COLLECT.value == "collect"
        assert QueueMode.STEER_BACKLOG.value == "steer_backlog"
        assert QueueMode.INTERRUPT.value == "interrupt"
        assert QueueMode.QUEUE.value == "queue"

    def test_queue_mode_count(self):
        """Test QueueMode has all expected members."""
        assert len(QueueMode) == 6


class TestDropPolicy:
    """Tests for DropPolicy enum."""

    def test_drop_policy_values(self):
        """Test all DropPolicy values."""
        assert DropPolicy.OLD.value == "old"
        assert DropPolicy.NEW.value == "new"
        assert DropPolicy.SUMMARIZE.value == "summarize"

    def test_drop_policy_count(self):
        """Test DropPolicy has all expected members."""
        assert len(DropPolicy) == 3


class TestQueueSettings:
    """Tests for QueueSettings dataclass."""

    def test_default_values(self):
        """Test QueueSettings default values."""
        settings = QueueSettings()
        assert settings.mode == QueueMode.COLLECT
        assert settings.max_size == 100
        assert settings.drop_policy == DropPolicy.NEW
        assert settings.ttl_seconds is None

    def test_custom_values(self):
        """Test QueueSettings with custom values."""
        settings = QueueSettings(
            mode=QueueMode.STEER,
            max_size=50,
            drop_policy=DropPolicy.OLD,
            ttl_seconds=300,
        )
        assert settings.mode == QueueMode.STEER
        assert settings.max_size == 50
        assert settings.drop_policy == DropPolicy.OLD
        assert settings.ttl_seconds == 300


class TestQueuedMessage:
    """Tests for QueuedMessage dataclass."""

    def test_create_message(self):
        """Test creating a QueuedMessage."""
        message = QueuedMessage(
            prompt="Hello world",
            session_key="session-1",
        )
        assert message.prompt == "Hello world"
        assert message.session_key == "session-1"
        assert message.message_id is not None
        assert message.timestamp is not None
        assert message.metadata == {}
        assert message.priority == 0

    def test_message_with_metadata(self):
        """Test QueuedMessage with metadata."""
        metadata = {"user": "test", "source": "api"}
        message = QueuedMessage(
            prompt="Test",
            session_key="session-1",
            metadata=metadata,
            priority=5,
        )
        assert message.metadata == metadata
        assert message.priority == 5


class TestQueueState:
    """Tests for QueueState dataclass."""

    def test_default_values(self):
        """Test QueueState default values."""
        state = QueueState(session_key="session-1")
        assert state.session_key == "session-1"
        assert state.messages == []
        assert state.mode == QueueMode.COLLECT
        assert state.is_processing is False
        assert state.last_activity is not None


class TestQueueManager:
    """Tests for QueueManager class."""

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_queue(self):
        """Test get_or_create creates a new queue."""
        manager = QueueManager()
        settings = QueueSettings(mode=QueueMode.COLLECT)

        queue = await manager.get_or_create("session-1", settings)

        assert queue.session_key == "session-1"
        assert queue.mode == QueueMode.COLLECT
        assert queue.messages == []

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(self):
        """Test get_or_create returns existing queue."""
        manager = QueueManager()
        settings = QueueSettings(mode=QueueMode.COLLECT)

        queue1 = await manager.get_or_create("session-1", settings)
        queue2 = await manager.get_or_create("session-1", settings)

        assert queue1 is queue2

    @pytest.mark.asyncio
    async def test_get_queue_returns_none_for_nonexistent(self):
        """Test get_queue returns None for nonexistent queue."""
        manager = QueueManager()
        queue = manager.get_queue("nonexistent")
        assert queue is None

    @pytest.mark.asyncio
    async def test_delete_queue(self):
        """Test deleting a queue."""
        manager = QueueManager()
        settings = QueueSettings()

        await manager.get_or_create("session-1", settings)
        result = await manager.delete_queue("session-1")

        assert result is True
        assert manager.get_queue("session-1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_queue(self):
        """Test deleting nonexistent queue returns False."""
        manager = QueueManager()
        result = await manager.delete_queue("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue(self):
        """Test enqueuing a message."""
        manager = QueueManager()
        settings = QueueSettings()
        await manager.get_or_create("session-1", settings)

        message = QueuedMessage(prompt="Test", session_key="session-1")
        result = await manager.enqueue("session-1", message)

        assert result is True
        assert len(manager._queues["session-1"].messages) == 1

    @pytest.mark.asyncio
    async def test_enqueue_nonexistent_queue(self):
        """Test enqueuing to nonexistent queue returns False."""
        manager = QueueManager()
        message = QueuedMessage(prompt="Test", session_key="session-1")
        result = await manager.enqueue("session-1", message)
        assert result is False

    @pytest.mark.asyncio
    async def test_dequeue(self):
        """Test dequeuing a message."""
        manager = QueueManager()
        settings = QueueSettings()
        await manager.get_or_create("session-1", settings)

        message1 = QueuedMessage(prompt="First", session_key="session-1", priority=1)
        message2 = QueuedMessage(prompt="Second", session_key="session-1", priority=0)
        await manager.enqueue("session-1", message1)
        await manager.enqueue("session_key-1", message2)

        # Note: we use a separate enqueue call for message2 since session_key is different
        await manager.enqueue("session-1", message2)

        dequeued = await manager.dequeue("session-1")

        assert dequeued is not None
        assert dequeued.prompt == "First"  # Higher priority first
        assert len(manager._queues["session-1"].messages) == 1

    @pytest.mark.asyncio
    async def test_peek(self):
        """Test peeking at the first message."""
        manager = QueueManager()
        settings = QueueSettings()
        await manager.get_or_create("session-1", settings)

        message = QueuedMessage(prompt="Test", session_key="session-1")
        await manager.enqueue("session-1", message)

        peeked = await manager.peek("session-1")

        assert peeked is not None
        assert peeked.prompt == "Test"
        assert len(manager._queues["session-1"].messages) == 1  # Still there

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing the queue."""
        manager = QueueManager()
        settings = QueueSettings()
        await manager.get_or_create("session-1", settings)

        await manager.enqueue("session-1", QueuedMessage(prompt="Test", session_key="session-1"))
        result = await manager.clear("session-1")

        assert result is True
        assert len(manager._queues["session-1"].messages) == 0

    @pytest.mark.asyncio
    async def test_list_queues(self):
        """Test listing all queues."""
        manager = QueueManager()
        settings = QueueSettings()

        await manager.get_or_create("session-1", settings)
        await manager.get_or_create("session-2", settings)

        queues = manager.list_queues()

        assert "session-1" in queues
        assert "session-2" in queues

    @pytest.mark.asyncio
    async def test_get_size(self):
        """Test getting queue size."""
        manager = QueueManager()
        settings = QueueSettings()
        await manager.get_or_create("session-1", settings)

        await manager.enqueue("session-1", QueuedMessage(prompt="Test1", session_key="session-1"))
        await manager.enqueue("session-1", QueuedMessage(prompt="Test2", session_key="session-1"))

        size = await manager.get_size("session-1")

        assert size == 2


class TestQAScenario:
    """Test QA scenarios from requirements."""

    @pytest.mark.asyncio
    async def test_qa_scenario(self):
        """Test the QA scenario from requirements."""
        from datacloud_agent.queue import QueueManager, QueueSettings, QueueMode

        manager = QueueManager()
        settings = QueueSettings(mode=QueueMode.COLLECT)
        queue = manager.get_queue("session-1")

        # Queue doesn't exist yet, should be None
        assert queue is None

        # Create the queue
        queue = await manager.get_or_create("session-1", settings)

        # Now it should exist with the correct mode
        assert queue is not None
        assert queue.mode == QueueMode.COLLECT
