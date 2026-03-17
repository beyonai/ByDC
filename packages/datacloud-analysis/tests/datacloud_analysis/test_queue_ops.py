"""Tests for queue operations (enqueuer and drainer)."""

import asyncio
import pytest

from datacloud_analysis.queue import (
    QueueManager,
    MessageEnqueuer,
    QueueDrainer,
    QueueSettings,
    QueuedMessage,
    DropPolicy,
    QueueMode,
)


class TestMessageEnqueuer:
    """Tests for MessageEnqueuer."""

    @pytest.mark.asyncio
    async def test_enqueue_success(self):
        """Test successful enqueue."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings(max_size=10)
        message = QueuedMessage(prompt="test", session_key="s1")

        success = await enqueuer.enqueue("s1", message, settings)
        assert success is True
        assert await enqueuer.get_queue_size("s1") == 1

    @pytest.mark.asyncio
    async def test_enqueue_duplicate(self):
        """Test duplicate detection."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings()
        message = QueuedMessage(prompt="same", session_key="s1")

        success1 = await enqueuer.enqueue("s1", message, settings)
        assert success1 is True

        # Second identical prompt within dedupe window should be rejected
        success2 = await enqueuer.enqueue("s1", message, settings)
        assert success2 is False

        # Wait longer than dedupe window (5 seconds) - we can't wait in test.
        # Instead we'll just test that deduplication works for immediate duplicate.

    @pytest.mark.asyncio
    async def test_enqueue_queue_full_new_policy(self):
        """Test queue full with NEW drop policy (reject)."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings(max_size=2, drop_policy=DropPolicy.NEW)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")
        msg3 = QueuedMessage(prompt="m3", session_key="s1")

        assert await enqueuer.enqueue("s1", msg1, settings) is True
        assert await enqueuer.enqueue("s1", msg2, settings) is True
        # Queue full, third message rejected
        assert await enqueuer.enqueue("s1", msg3, settings) is False
        assert await enqueuer.get_queue_size("s1") == 2

    @pytest.mark.asyncio
    async def test_enqueue_queue_full_old_policy(self):
        """Test queue full with OLD drop policy (drop oldest)."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings(max_size=2, drop_policy=DropPolicy.OLD)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")
        msg3 = QueuedMessage(prompt="m3", session_key="s1")

        assert await enqueuer.enqueue("s1", msg1, settings) is True
        assert await enqueuer.enqueue("s1", msg2, settings) is True
        # Queue full, third message triggers drop oldest (m1)
        assert await enqueuer.enqueue("s1", msg3, settings) is True
        size = await enqueuer.get_queue_size("s1")
        assert size == 2  # still max size
        # Check that m1 is gone, m2 and m3 remain
        # We can dequeue via manager to see order
        dequeued = await manager.dequeue("s1")
        assert (
            dequeued.prompt == "m2"
        )  # m2 is oldest remaining? Actually m2 older than m3, but priority same.
        dequeued2 = await manager.dequeue("s1")
        assert dequeued2.prompt == "m3"

    @pytest.mark.asyncio
    async def test_try_enqueue_reasons(self):
        """Test try_enqueue returns appropriate reasons."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings(max_size=1, drop_policy=DropPolicy.NEW)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")

        success, reason = await enqueuer.try_enqueue("s1", msg1, settings)
        assert success is True
        assert reason == ""

        success, reason = await enqueuer.try_enqueue("s1", msg1, settings)
        assert success is False
        assert reason == "duplicate"

        success, reason = await enqueuer.try_enqueue("s1", msg2, settings)
        assert success is False
        assert reason == "queue_full"

    @pytest.mark.asyncio
    async def test_get_queue_size(self):
        """Test get_queue_size."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        settings = QueueSettings()
        msg = QueuedMessage(prompt="test", session_key="s1")

        assert await enqueuer.get_queue_size("s1") == 0
        await enqueuer.enqueue("s1", msg, settings)
        assert await enqueuer.get_queue_size("s1") == 1


class TestQueueDrainer:
    """Tests for QueueDrainer."""

    @pytest.mark.asyncio
    async def test_drain_individual(self):
        """Test draining messages individually."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        settings = QueueSettings()
        # Need to enqueue messages via manager
        await manager.get_or_create("s1", settings)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")
        await manager.enqueue("s1", msg1)
        await manager.enqueue("s1", msg2)

        processed = []

        async def processor(msg: QueuedMessage):
            processed.append(msg.prompt)
            return len(processed)

        results = await drainer.drain("s1", processor)
        assert processed == ["m1", "m2"]
        assert results == [1, 2]
        assert await manager.get_size("s1") == 0

    @pytest.mark.asyncio
    async def test_drain_collect(self):
        """Test draining messages in collect mode."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        settings = QueueSettings()
        await manager.get_or_create("s1", settings)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")
        await manager.enqueue("s1", msg1)
        await manager.enqueue("s1", msg2)

        collected = []

        async def processor(msgs: list[QueuedMessage]):
            collected.extend([m.prompt for m in msgs])
            return len(collected)

        result = await drainer.drain_collect("s1", processor)
        assert collected == ["m1", "m2"]
        assert result == 2
        assert await manager.get_size("s1") == 0

    @pytest.mark.asyncio
    async def test_drain_empty(self):
        """Test draining empty queue."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        settings = QueueSettings()
        await manager.get_or_create("s1", settings)

        processed = []

        async def processor(msg: QueuedMessage):
            processed.append(msg.prompt)

        results = await drainer.drain("s1", processor)
        assert results == []
        assert processed == []

    @pytest.mark.asyncio
    async def test_background_drain(self):
        """Test starting and stopping background drain."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        settings = QueueSettings(mode=QueueMode.QUEUE)
        await manager.get_or_create("s1", settings)
        msg = QueuedMessage(prompt="test", session_key="s1")
        await manager.enqueue("s1", msg)

        processed = []

        async def processor(msg: QueuedMessage):
            processed.append(msg.prompt)

        # Start background drain with short interval
        drainer.start_background_drain("s1", processor, interval=0.1)
        assert drainer.is_draining("s1") is True

        # Wait a bit for processing
        await asyncio.sleep(0.3)
        # Stop background drain
        stopped = drainer.stop_background_drain("s1")
        assert stopped is True
        assert drainer.is_draining("s1") is False

        # Ensure message was processed
        assert processed == ["test"]
        assert await manager.get_size("s1") == 0

    @pytest.mark.asyncio
    async def test_stop_background_drain_nonexistent(self):
        """Test stopping background drain when none exists."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        stopped = drainer.stop_background_drain("nonexistent")
        assert stopped is False

    @pytest.mark.asyncio
    async def test_background_drain_multiple_messages(self):
        """Test background drain processes multiple messages."""
        manager = QueueManager()
        drainer = QueueDrainer(manager)
        settings = QueueSettings(mode=QueueMode.QUEUE)
        await manager.get_or_create("s1", settings)
        msg1 = QueuedMessage(prompt="m1", session_key="s1")
        msg2 = QueuedMessage(prompt="m2", session_key="s1")
        await manager.enqueue("s1", msg1)
        await manager.enqueue("s1", msg2)

        processed = []

        async def processor(msg: QueuedMessage):
            processed.append(msg.prompt)

        # Start background drain
        drainer.start_background_drain("s1", processor, interval=0.1)
        await asyncio.sleep(0.3)
        drainer.stop_background_drain("s1")

        assert set(processed) == {"m1", "m2"}
        assert await manager.get_size("s1") == 0


class TestIntegration:
    """Integration tests for enqueuer and drainer together."""

    @pytest.mark.asyncio
    async def test_enqueue_drain_flow(self):
        """Test full flow: enqueue messages, then drain."""
        manager = QueueManager()
        enqueuer = MessageEnqueuer(manager)
        drainer = QueueDrainer(manager)
        settings = QueueSettings(max_size=5)

        messages = [QueuedMessage(prompt=f"msg{i}", session_key="session1") for i in range(3)]
        for msg in messages:
            await enqueuer.enqueue("session1", msg, settings)

        assert await enqueuer.get_queue_size("session1") == 3

        drained = []

        async def processor(msg: QueuedMessage):
            drained.append(msg.prompt)
            return msg.prompt

        results = await drainer.drain("session1", processor)
        assert drained == ["msg0", "msg1", "msg2"]
        assert results == ["msg0", "msg1", "msg2"]
        assert await enqueuer.get_queue_size("session1") == 0
