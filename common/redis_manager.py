"""
Redis Manager for A2A State Management

Handles:
- Task state persistence
- Subscription management across distributed pods
- Pub/Sub for real-time status broadcasting
- Task status streaming via Redis Streams
"""

import asyncio
import json
from typing import AsyncGenerator, Dict, List, Optional, Any
from datetime import datetime, timedelta

import redis.asyncio as redis
import structlog

from .a2a_protocol import (
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)


logger = structlog.get_logger()


class RedisManager:
    """
    Redis manager for A2A protocol state management.
    
    Uses Redis for:
    1. Task State Storage - Persist task state across agent restarts
    2. Pub/Sub - Broadcast status updates to all subscribers
    3. Subscription Tracking - Track active subscriptions per task
    4. Streams - Ordered event log for resubscription support
    
    Key Structure:
    - task:{task_id} - Hash storing task state
    - task:{task_id}:stream - Stream of events for the task
    - subscriptions:{task_id} - Set of subscriber agent names
    - channel:task:{task_id} - Pub/Sub channel for live updates
    """
    
    TASK_KEY_PREFIX = "task:"
    STREAM_KEY_SUFFIX = ":stream"
    SUBSCRIPTIONS_PREFIX = "subscriptions:"
    CHANNEL_PREFIX = "channel:task:"
    
    # TTL for task data (24 hours default)
    TASK_TTL = 60 * 60 * 24
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        password: Optional[str] = None,
        db: int = 0,
    ):
        self.url = url
        self.password = password
        self.db = db
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        
    async def connect(self):
        """Connect to Redis."""
        self._client = redis.Redis.from_url(
            self.url,
            password=self.password,
            db=self.db,
            decode_responses=True,
        )
        await self._client.ping()
        logger.info("Connected to Redis", url=self.url)
        
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._pubsub:
            await self._pubsub.close()
        if self._client:
            await self._client.close()
        logger.info("Disconnected from Redis")
        
    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client
    
    # =========================================================================
    # Task State Management
    # =========================================================================
    
    async def store_task(self, task: Task) -> None:
        """Store a task in Redis."""
        key = f"{self.TASK_KEY_PREFIX}{task.id}"
        data = task.model_dump_json()
        
        await self.client.set(key, data, ex=self.TASK_TTL)
        logger.debug("Stored task", task_id=task.id)
        
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task from Redis."""
        key = f"{self.TASK_KEY_PREFIX}{task_id}"
        data = await self.client.get(key)
        
        if data:
            return Task(**json.loads(data))
        return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> None:
        """Update task status and refresh TTL."""
        task = await self.get_task(task_id)
        if task:
            task.status = status
            await self.store_task(task)
            
    async def delete_task(self, task_id: str) -> None:
        """Delete a task from Redis."""
        keys = [
            f"{self.TASK_KEY_PREFIX}{task_id}",
            f"{self.TASK_KEY_PREFIX}{task_id}{self.STREAM_KEY_SUFFIX}",
            f"{self.SUBSCRIPTIONS_PREFIX}{task_id}",
        ]
        await self.client.delete(*keys)
        logger.debug("Deleted task", task_id=task_id)
        
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    async def add_subscription(
        self,
        task_id: str,
        subscriber: str,
    ) -> None:
        """Add a subscriber to a task."""
        key = f"{self.SUBSCRIPTIONS_PREFIX}{task_id}"
        await self.client.sadd(key, subscriber)
        await self.client.expire(key, self.TASK_TTL)
        logger.debug("Added subscription", task_id=task_id, subscriber=subscriber)
        
    async def remove_subscription(
        self,
        task_id: str,
        subscriber: str,
    ) -> None:
        """Remove a subscriber from a task."""
        key = f"{self.SUBSCRIPTIONS_PREFIX}{task_id}"
        await self.client.srem(key, subscriber)
        logger.debug("Removed subscription", task_id=task_id, subscriber=subscriber)
        
    async def get_subscribers(self, task_id: str) -> List[str]:
        """Get all subscribers for a task."""
        key = f"{self.SUBSCRIPTIONS_PREFIX}{task_id}"
        return list(await self.client.smembers(key))
    
    async def has_subscribers(self, task_id: str) -> bool:
        """Check if a task has any active subscribers."""
        key = f"{self.SUBSCRIPTIONS_PREFIX}{task_id}"
        return await self.client.scard(key) > 0
    
    # =========================================================================
    # Pub/Sub for Real-time Updates
    # =========================================================================
    
    async def publish_status(
        self,
        task_id: str,
        event: TaskStatusUpdateEvent,
    ) -> None:
        """Publish a status update to all subscribers."""
        channel = f"{self.CHANNEL_PREFIX}{task_id}"
        message = {
            "type": "status",
            "data": event.model_dump(),
        }
        await self.client.publish(channel, json.dumps(message))
        
        # Also add to stream for resubscription
        await self._add_to_stream(task_id, "status", event.model_dump())
        logger.debug("Published status", task_id=task_id, state=event.status.state)
        
    async def publish_artifact(
        self,
        task_id: str,
        event: TaskArtifactUpdateEvent,
    ) -> None:
        """Publish an artifact update to all subscribers."""
        channel = f"{self.CHANNEL_PREFIX}{task_id}"
        message = {
            "type": "artifact",
            "data": event.model_dump(),
        }
        await self.client.publish(channel, json.dumps(message))
        
        # Also add to stream for resubscription
        await self._add_to_stream(task_id, "artifact", event.model_dump())
        logger.debug("Published artifact", task_id=task_id)
        
    async def subscribe_to_task(
        self,
        task_id: str,
        from_beginning: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to real-time updates for a task.
        
        Uses Pub/Sub for live updates. If from_beginning is True,
        first replays events from the stream.
        
        Yields:
            SSE-formatted event dictionaries
        """
        channel = f"{self.CHANNEL_PREFIX}{task_id}"
        
        # Replay from stream if requested
        if from_beginning:
            async for event in self._read_stream(task_id):
                yield event
        
        # Subscribe to live updates
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message.get("type") == "message":
                    data = json.loads(message["data"])
                    event_type = data.get("type")
                    event_data = data.get("data")
                    
                    yield {
                        "event": event_type,
                        "data": json.dumps(event_data),
                    }
                    
                    # Check for terminal state
                    if event_type == "status" and event_data.get("final"):
                        break
                        
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            
    # =========================================================================
    # Redis Streams for Event History
    # =========================================================================
    
    async def _add_to_stream(
        self,
        task_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Add an event to the task's stream."""
        key = f"{self.TASK_KEY_PREFIX}{task_id}{self.STREAM_KEY_SUFFIX}"
        await self.client.xadd(
            key,
            {
                "type": event_type,
                "data": json.dumps(data),
                "timestamp": datetime.utcnow().isoformat(),
            },
            maxlen=1000,  # Keep last 1000 events per task
        )
        await self.client.expire(key, self.TASK_TTL)
        
    async def _read_stream(
        self,
        task_id: str,
        start: str = "0",
        count: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Read events from a task's stream."""
        key = f"{self.TASK_KEY_PREFIX}{task_id}{self.STREAM_KEY_SUFFIX}"
        
        messages = await self.client.xrange(key, min=start, count=count)
        
        for msg_id, fields in messages:
            event_type = fields.get("type")
            data = json.loads(fields.get("data", "{}"))
            
            yield {
                "event": event_type,
                "data": json.dumps(data),
            }
            
    async def get_stream_events(
        self,
        task_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all events from a task's stream."""
        events = []
        async for event in self._read_stream(task_id, count=limit):
            events.append(event)
        return events
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    async def get_active_tasks(
        self,
        pattern: str = "*",
    ) -> List[str]:
        """Get all active task IDs matching a pattern."""
        cursor = 0
        task_ids = []
        
        while True:
            cursor, keys = await self.client.scan(
                cursor=cursor,
                match=f"{self.TASK_KEY_PREFIX}{pattern}",
                count=100,
            )
            
            for key in keys:
                # Skip stream keys
                if not key.endswith(self.STREAM_KEY_SUFFIX):
                    task_id = key.replace(self.TASK_KEY_PREFIX, "")
                    task_ids.append(task_id)
                    
            if cursor == 0:
                break
                
        return task_ids
    
    async def cleanup_completed_tasks(
        self,
        max_age_hours: int = 24,
    ) -> int:
        """
        Clean up completed tasks older than max_age.
        Returns number of tasks deleted.
        """
        deleted = 0
        task_ids = await self.get_active_tasks()
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        for task_id in task_ids:
            task = await self.get_task(task_id)
            if task and task.status.state in [
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELED,
            ]:
                if task.status.timestamp:
                    task_time = datetime.fromisoformat(task.status.timestamp)
                    if task_time < cutoff:
                        await self.delete_task(task_id)
                        deleted += 1
                        
        logger.info("Cleaned up completed tasks", deleted=deleted)
        return deleted

