"""Test queue drop policies."""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_agent.queue.manager import QueueManager
from datacloud_agent.queue.types import (
    DropPolicy,
    QueuedMessage,
    QueueMode,
    QueueSettings,
    QueueState,
)


@pytest.fixture
def queue_manager():
    """Create a QueueManager instance."""
    return QueueManager()


@pytest.fixture
def mock_settings():
    """Create queue settings with SUMMARIZE policy."""
    return QueueSettings(
        mode=QueueMode.COLLECT,
        max_size=100,
        drop_policy=DropPolicy.SUMMARIZE,
    )


@pytest.mark.asyncio
async def test_enqueue_with_old_policy(queue_manager):
    """Test OLD drop policy - should drop oldest message when queue is full."""
    session_key = "test-session-old"

    # Create queue with OLD policy stored in message metadata
    settings = QueueSettings(
        mode=QueueMode.COLLECT,
        max_size=3,
        drop_policy=DropPolicy.OLD,
    )

    # Initialize queue
    queue_state = await queue_manager.get_or_create(session_key, settings)

    # Fill queue to max
    for i in range(3):
        msg = QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            metadata={"drop_policy": DropPolicy.OLD},
        )
        result = await queue_manager.enqueue(session_key, msg)
        assert result is True

    # Verify queue is full
    size = await queue_manager.get_size(session_key)
    assert size == 3

    # Add one more message - should drop oldest
    new_msg = QueuedMessage(
        prompt="New message",
        session_key=session_key,
        metadata={"drop_policy": DropPolicy.OLD},
    )
    result = await queue_manager.enqueue(session_key, new_msg)
    assert result is True

    # Size should still be 3 (dropped oldest)
    size = await queue_manager.get_size(session_key)
    assert size == 3


@pytest.mark.asyncio
async def test_enqueue_with_new_policy(queue_manager):
    """Test NEW drop policy - should reject new messages when queue is full."""
    session_key = "test-session-new"

    # Create queue with NEW policy
    settings = QueueSettings(
        mode=QueueMode.COLLECT,
        max_size=2,
        drop_policy=DropPolicy.NEW,
    )

    # Initialize queue
    queue_state = await queue_manager.get_or_create(session_key, settings)

    # Fill queue to max
    for i in range(2):
        msg = QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            metadata={"drop_policy": DropPolicy.NEW},
        )
        result = await queue_manager.enqueue(session_key, msg)
        assert result is True

    # Verify queue is full
    size = await queue_manager.get_size(session_key)
    assert size == 2

    # Try to add one more message - should be rejected
    new_msg = QueuedMessage(
        prompt="Rejected message",
        session_key=session_key,
        metadata={"drop_policy": DropPolicy.NEW},
    )
    result = await queue_manager.enqueue(session_key, new_msg)
    assert result is False

    # Size should still be 2
    size = await queue_manager.get_size(session_key)
    assert size == 2


@pytest.mark.asyncio
async def test_enqueue_with_summarize_policy_less_than_10_messages(queue_manager):
    """Test SUMMARIZE policy with fewer than 10 messages - should drop oldest."""
    session_key = "test-session-summarize-few"

    # Create queue with SUMMARIZE policy
    settings = QueueSettings(
        mode=QueueMode.COLLECT,
        max_size=5,
        drop_policy=DropPolicy.SUMMARIZE,
    )

    # Initialize queue
    queue_state = await queue_manager.get_or_create(session_key, settings)

    # Fill queue to max (less than 10 messages)
    for i in range(5):
        msg = QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            metadata={"drop_policy": DropPolicy.SUMMARIZE},
        )
        result = await queue_manager.enqueue(session_key, msg)
        assert result is True

    # Verify queue is full
    size = await queue_manager.get_size(session_key)
    assert size == 5

    # Add one more message - should drop oldest (since < 10 messages)
    new_msg = QueuedMessage(
        prompt="New message",
        session_key=session_key,
        metadata={"drop_policy": DropPolicy.SUMMARIZE},
    )
    result = await queue_manager.enqueue(session_key, new_msg)
    assert result is True

    # Size should still be 5 (dropped oldest, no summarization)
    size = await queue_manager.get_size(session_key)
    assert size == 5


@pytest.mark.asyncio
async def test_enqueue_with_summarize_policy_many_messages(queue_manager):
    """Test SUMMARIZE policy with 10+ messages - should summarize old ones."""
    session_key = "test-session-summarize-many"

    # Create queue with SUMMARIZE policy
    settings = QueueSettings(
        mode=QueueMode.COLLECT,
        max_size=15,
        drop_policy=DropPolicy.SUMMARIZE,
    )

    # Initialize queue
    queue_state = await queue_manager.get_or_create(session_key, settings)

    # Fill queue to max (more than 10 messages)
    for i in range(15):
        msg = QueuedMessage(
            prompt=f"Message {i} with some content to summarize",
            session_key=session_key,
            metadata={"drop_policy": DropPolicy.SUMMARIZE},
        )
        result = await queue_manager.enqueue(session_key, msg)
        assert result is True

    # Verify queue is full
    size = await queue_manager.get_size(session_key)
    assert size == 15

    # Mock the summarization to avoid actual API calls
    with patch.object(queue_manager, "_async_summarize", new_callable=AsyncMock) as mock_summarize:
        # Add one more message - should trigger summarization
        new_msg = QueuedMessage(
            prompt="New message",
            session_key=session_key,
            metadata={"drop_policy": DropPolicy.SUMMARIZE},
        )
        result = await queue_manager.enqueue(session_key, new_msg)
        assert result is True

        # Give async task time to start
        await asyncio.sleep(0.1)

        # Verify summarization was called
        mock_summarize.assert_called_once()

        # Check that 5 messages were summarized (15 - 10 = 5)
        call_args = mock_summarize.call_args
        assert len(call_args[0][1]) == 5  # messages_to_summarize


@pytest.mark.asyncio
async def test_summarize_async_with_mocked_agent(queue_manager):
    """Test async summarization with mocked agent."""
    session_key = "test-session-summarize-async"

    # Create queue state
    messages = [
        QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            timestamp=datetime.now(),
        )
        for i in range(5)
    ]

    # Set API key for test
    os.environ["OPENAI_API_KEY"] = "test-key"

    # Mock the agent creation and invocation
    with (
        patch("datacloud_agent.queue.manager.init_chat_model") as mock_init_model,
        patch("datacloud_agent.queue.manager.create_deep_agent") as mock_create_agent,
    ):
        # Setup mock agent
        mock_model = MagicMock()
        mock_init_model.return_value = mock_model

        mock_agent = AsyncMock()
        mock_response = {"messages": [MagicMock(content="This is a summary of old messages.")]}
        mock_agent.ainvoke = AsyncMock(return_value=mock_response)
        mock_create_agent.return_value = mock_agent

        # Initialize queue
        queue_state = QueueState(
            session_key=session_key,
            messages=[],
            mode=QueueMode.COLLECT,
        )
        queue_manager._queues[session_key] = queue_state

        # Call summarization
        await queue_manager._async_summarize(session_key, messages)

        # Verify summary message was inserted
        size = await queue_manager.get_size(session_key)
        assert size == 1

        # Verify summary content
        queue_state = queue_manager.get_queue(session_key)
        assert len(queue_state.messages) == 1
        assert "[历史消息总结]" in queue_state.messages[0].prompt
        assert queue_state.messages[0].priority == 10
        assert queue_state.messages[0].metadata.get("is_summary") is True
        assert queue_state.messages[0].metadata.get("message_count") == 5

    # Clean up
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_summarize_async_without_api_key(queue_manager):
    """Test that summarization gracefully handles missing API key."""
    session_key = "test-session-no-api-key"

    # Create queue state
    messages = [
        QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            timestamp=datetime.now(),
        )
        for i in range(5)
    ]

    # Initialize queue
    queue_state = QueueState(
        session_key=session_key,
        messages=[],
        mode=QueueMode.COLLECT,
    )
    queue_manager._queues[session_key] = queue_state

    # Temporarily remove API key
    original_key = os.environ.get("OPENAI_API_KEY")
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]

    try:
        # Call summarization - should handle gracefully
        await queue_manager._async_summarize(session_key, messages)

        # Verify no message was inserted (failed silently)
        size = await queue_manager.get_size(session_key)
        assert size == 0
    finally:
        # Restore API key
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key


@pytest.mark.asyncio
async def test_summarize_async_with_exception(queue_manager):
    """Test that summarization handles exceptions gracefully."""
    session_key = "test-session-exception"

    # Create queue state
    messages = [
        QueuedMessage(
            prompt=f"Message {i}",
            session_key=session_key,
            timestamp=datetime.now(),
        )
        for i in range(5)
    ]

    # Mock agent to raise exception
    with patch("datacloud_agent.queue.manager.init_chat_model") as mock_init_model:
        mock_init_model.side_effect = Exception("API Error")

        # Initialize queue
        queue_state = QueueState(
            session_key=session_key,
            messages=[],
            mode=QueueMode.COLLECT,
        )
        queue_manager._queues[session_key] = queue_state

        # Call summarization - should handle exception
        await queue_manager._async_summarize(session_key, messages)

        # Verify no message was inserted (failed silently)
        size = await queue_manager.get_size(session_key)
        assert size == 0


@pytest.mark.asyncio
async def test_dequeue_order(queue_manager):
    """Test that dequeue returns messages in correct order."""
    session_key = "test-session-dequeue"

    # Create queue
    settings = QueueSettings(mode="collect", max_size=10)
    await queue_manager.get_or_create(session_key, settings)

    # Add messages with different priorities
    msg1 = QueuedMessage(prompt="Low priority", session_key=session_key, priority=1)
    msg2 = QueuedMessage(prompt="High priority", session_key=session_key, priority=10)
    msg3 = QueuedMessage(prompt="Medium priority", session_key=session_key, priority=5)

    await queue_manager.enqueue(session_key, msg1)
    await queue_manager.enqueue(session_key, msg2)
    await queue_manager.enqueue(session_key, msg3)

    # Dequeue should return highest priority first
    dequeued = await queue_manager.dequeue(session_key)
    assert dequeued is not None
    assert dequeued.prompt == "High priority"

    dequeued = await queue_manager.dequeue(session_key)
    assert dequeued is not None
    assert dequeued.prompt == "Medium priority"

    dequeued = await queue_manager.dequeue(session_key)
    assert dequeued is not None
    assert dequeued.prompt == "Low priority"


@pytest.mark.asyncio
async def test_queue_isolation(queue_manager):
    """Test that different sessions have isolated queues."""
    session1 = "session-1"
    session2 = "session-2"

    # Create queues for both sessions
    settings = QueueSettings(mode="collect", max_size=10)
    await queue_manager.get_or_create(session1, settings)
    await queue_manager.get_or_create(session2, settings)

    # Add messages to session1
    msg1 = QueuedMessage(prompt="Session 1 message", session_key=session1)
    await queue_manager.enqueue(session1, msg1)

    # Add messages to session2
    msg2 = QueuedMessage(prompt="Session 2 message", session_key=session2)
    await queue_manager.enqueue(session2, msg2)

    # Verify isolation
    size1 = await queue_manager.get_size(session1)
    size2 = await queue_manager.get_size(session2)

    assert size1 == 1
    assert size2 == 1

    # Dequeue from session1
    dequeued = await queue_manager.dequeue(session1)
    assert dequeued.prompt == "Session 1 message"

    # Session2 should still have its message
    size2 = await queue_manager.get_size(session2)
    assert size2 == 1
