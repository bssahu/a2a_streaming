"""
Tests for Redis Manager.
"""

import pytest
import asyncio
from datetime import datetime

from common.redis_manager import RedisManager
from common.a2a_protocol import (
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Artifact,
    TextPart,
)


@pytest.mark.asyncio
class TestRedisManagerTaskStorage:
    """Tests for task storage functionality."""
    
    async def test_store_and_get_task(self, redis_manager: RedisManager):
        """Test storing and retrieving a task."""
        task = Task(
            id="test-task-1",
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        
        await redis_manager.store_task(task)
        retrieved = await redis_manager.get_task("test-task-1")
        
        assert retrieved is not None
        assert retrieved.id == task.id
        assert retrieved.status.state == TaskState.SUBMITTED
    
    async def test_get_nonexistent_task(self, redis_manager: RedisManager):
        """Test getting a task that doesn't exist."""
        retrieved = await redis_manager.get_task("nonexistent-task")
        assert retrieved is None
    
    async def test_update_task_status(self, redis_manager: RedisManager):
        """Test updating task status."""
        task = Task(
            id="test-task-2",
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        await redis_manager.store_task(task)
        
        await redis_manager.update_task_status(
            "test-task-2",
            TaskStatus(state=TaskState.WORKING),
        )
        
        retrieved = await redis_manager.get_task("test-task-2")
        assert retrieved.status.state == TaskState.WORKING
    
    async def test_delete_task(self, redis_manager: RedisManager):
        """Test deleting a task."""
        task = Task(
            id="test-task-3",
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        await redis_manager.store_task(task)
        
        await redis_manager.delete_task("test-task-3")
        
        retrieved = await redis_manager.get_task("test-task-3")
        assert retrieved is None


@pytest.mark.asyncio
class TestRedisManagerSubscriptions:
    """Tests for subscription management."""
    
    async def test_add_subscription(self, redis_manager: RedisManager):
        """Test adding a subscription."""
        await redis_manager.add_subscription("task-sub-1", "agent-1")
        
        subscribers = await redis_manager.get_subscribers("task-sub-1")
        assert "agent-1" in subscribers
    
    async def test_multiple_subscriptions(self, redis_manager: RedisManager):
        """Test multiple subscriptions to same task."""
        await redis_manager.add_subscription("task-sub-2", "agent-1")
        await redis_manager.add_subscription("task-sub-2", "agent-2")
        
        subscribers = await redis_manager.get_subscribers("task-sub-2")
        assert len(subscribers) == 2
        assert "agent-1" in subscribers
        assert "agent-2" in subscribers
    
    async def test_remove_subscription(self, redis_manager: RedisManager):
        """Test removing a subscription."""
        await redis_manager.add_subscription("task-sub-3", "agent-1")
        await redis_manager.add_subscription("task-sub-3", "agent-2")
        
        await redis_manager.remove_subscription("task-sub-3", "agent-1")
        
        subscribers = await redis_manager.get_subscribers("task-sub-3")
        assert "agent-1" not in subscribers
        assert "agent-2" in subscribers
    
    async def test_has_subscribers(self, redis_manager: RedisManager):
        """Test checking if task has subscribers."""
        assert not await redis_manager.has_subscribers("task-sub-4")
        
        await redis_manager.add_subscription("task-sub-4", "agent-1")
        assert await redis_manager.has_subscribers("task-sub-4")


@pytest.mark.asyncio
class TestRedisManagerPubSub:
    """Tests for Pub/Sub functionality."""
    
    async def test_publish_status(self, redis_manager: RedisManager):
        """Test publishing a status update."""
        event = TaskStatusUpdateEvent(
            id="task-pubsub-1",
            status=TaskStatus(state=TaskState.WORKING),
        )
        
        # Should not raise
        await redis_manager.publish_status("task-pubsub-1", event)
    
    async def test_publish_artifact(self, redis_manager: RedisManager):
        """Test publishing an artifact update."""
        event = TaskArtifactUpdateEvent(
            id="task-pubsub-2",
            artifact=Artifact(
                name="test-artifact",
                parts=[TextPart(text="Test content")],
            ),
        )
        
        # Should not raise
        await redis_manager.publish_artifact("task-pubsub-2", event)


@pytest.mark.asyncio
class TestRedisManagerStreams:
    """Tests for Redis Streams functionality."""
    
    async def test_stream_events_are_stored(self, redis_manager: RedisManager):
        """Test that events are stored in stream."""
        task_id = "task-stream-1"
        
        # Publish some events
        await redis_manager.publish_status(
            task_id,
            TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(state=TaskState.WORKING),
            ),
        )
        await redis_manager.publish_artifact(
            task_id,
            TaskArtifactUpdateEvent(
                id=task_id,
                artifact=Artifact(
                    name="result",
                    parts=[TextPart(text="Result")],
                ),
            ),
        )
        
        # Read events from stream
        events = await redis_manager.get_stream_events(task_id)
        
        assert len(events) == 2
        assert events[0]["event"] == "status"
        assert events[1]["event"] == "artifact"
    
    async def test_stream_respects_limit(self, redis_manager: RedisManager):
        """Test that stream respects event limit."""
        task_id = "task-stream-2"
        
        # Publish multiple events
        for i in range(5):
            await redis_manager.publish_status(
                task_id,
                TaskStatusUpdateEvent(
                    id=task_id,
                    status=TaskStatus(state=TaskState.WORKING),
                ),
            )
        
        # Read with limit
        events = await redis_manager.get_stream_events(task_id, limit=3)
        assert len(events) == 3


@pytest.mark.asyncio
class TestRedisManagerUtilities:
    """Tests for utility functions."""
    
    async def test_get_active_tasks(self, redis_manager: RedisManager):
        """Test getting active tasks."""
        # Create some tasks
        for i in range(3):
            task = Task(
                id=f"active-task-{i}",
                status=TaskStatus(state=TaskState.WORKING),
            )
            await redis_manager.store_task(task)
        
        task_ids = await redis_manager.get_active_tasks()
        
        assert len(task_ids) >= 3
        assert "active-task-0" in task_ids
        assert "active-task-1" in task_ids
        assert "active-task-2" in task_ids



