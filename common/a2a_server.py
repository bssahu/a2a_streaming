"""
A2A Server Base Implementation

Provides the foundation for creating A2A-compliant agent servers
with support for streaming status updates via SSE.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Callable, Dict, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import structlog

from .a2a_protocol import (
    AgentCard,
    Task,
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    Artifact,
    TaskSendParams,
    SendTaskRequest,
    SendTaskResponse,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    generate_id,
)
from .redis_manager import RedisManager


logger = structlog.get_logger()


class A2AServer(ABC):
    """
    Base class for A2A-compliant agent servers.
    
    Implements the core A2A protocol endpoints:
    - GET /.well-known/agent.json - Agent Card
    - POST /tasks/send - Send task (non-streaming)
    - POST /tasks/sendSubscribe - Send task with SSE streaming
    - POST /tasks/resubscribe - Resubscribe to task updates
    - POST /tasks/get - Get task status
    - POST /tasks/cancel - Cancel a task
    """
    
    def __init__(
        self,
        agent_card: AgentCard,
        redis_manager: Optional[RedisManager] = None,
    ):
        self.agent_card = agent_card
        self.redis = redis_manager
        self.tasks: Dict[str, Task] = {}  # In-memory task store (Redis-backed in production)
        self.active_subscriptions: Dict[str, asyncio.Queue] = {}
        
    @abstractmethod
    async def process_task(
        self,
        task_id: str,
        message: Message,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Process a task and yield status/artifact updates.
        
        This method should be implemented by subclasses to define
        the agent's task processing logic.
        
        Yields:
            TaskStatusUpdateEvent or TaskArtifactUpdateEvent
        """
        pass
    
    def create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            if self.redis:
                await self.redis.connect()
                logger.info("Connected to Redis", agent=self.agent_card.name)
            yield
            # Shutdown
            if self.redis:
                await self.redis.disconnect()
                
        app = FastAPI(
            title=self.agent_card.name,
            description=self.agent_card.description,
            version=self.agent_card.version,
            lifespan=lifespan,
        )
        
        # Register routes
        self._register_routes(app)
        
        return app
    
    def _register_routes(self, app: FastAPI):
        """Register A2A protocol routes."""
        
        @app.get("/.well-known/agent.json")
        async def get_agent_card():
            """Return the agent card."""
            return self.agent_card.model_dump(exclude_none=True)
        
        @app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "agent": self.agent_card.name}
        
        @app.post("/tasks/send")
        async def send_task(request: Request):
            """
            Send a task and wait for completion (non-streaming).
            Returns the final task state.
            """
            body = await request.json()
            logger.info("Received tasks/send", body=body)
            
            try:
                req = SendTaskRequest(**body)
                params = req.params
                
                # Create initial task
                task = Task(
                    id=params.id,
                    sessionId=params.sessionId,
                    status=TaskStatus(state=TaskState.SUBMITTED),
                    history=[params.message],
                    metadata=params.metadata,
                )
                self.tasks[task.id] = task
                
                # Store in Redis if available
                if self.redis:
                    await self.redis.store_task(task)
                
                # Process task and collect all updates
                final_status = None
                artifacts = []
                
                async for event in self.process_task(
                    task.id,
                    params.message,
                    params.sessionId,
                    params.metadata,
                ):
                    if isinstance(event, TaskStatusUpdateEvent):
                        final_status = event.status
                        if self.redis:
                            await self.redis.publish_status(task.id, event)
                    elif isinstance(event, TaskArtifactUpdateEvent):
                        artifacts.append(event.artifact)
                        if self.redis:
                            await self.redis.publish_artifact(task.id, event)
                
                # Update task with final state
                task.status = final_status or TaskStatus(state=TaskState.COMPLETED)
                task.artifacts = artifacts if artifacts else None
                self.tasks[task.id] = task
                
                if self.redis:
                    await self.redis.store_task(task)
                
                return SendTaskResponse(
                    id=req.id,
                    result=task,
                ).model_dump(exclude_none=True)
                
            except Exception as e:
                logger.error("Error processing task", error=str(e))
                return SendTaskResponse(
                    id=body.get("id", generate_id()),
                    error={"code": -32000, "message": str(e)},
                ).model_dump(exclude_none=True)
        
        @app.post("/tasks/sendSubscribe")
        async def send_subscribe(request: Request):
            """
            Send a task with SSE streaming for real-time updates.
            This is the primary method for A2A communication with status streaming.
            """
            body = await request.json()
            logger.info("Received tasks/sendSubscribe", body=body)
            
            try:
                req = SendTaskRequest(**body)
                params = req.params
                
                # Create initial task
                task = Task(
                    id=params.id,
                    sessionId=params.sessionId,
                    status=TaskStatus(state=TaskState.SUBMITTED),
                    history=[params.message],
                    metadata=params.metadata,
                )
                self.tasks[task.id] = task
                
                if self.redis:
                    await self.redis.store_task(task)
                    await self.redis.add_subscription(task.id, self.agent_card.name)
                
                async def event_generator():
                    """Generate SSE events from task processing."""
                    try:
                        # Send initial submitted status
                        initial_event = TaskStatusUpdateEvent(
                            id=task.id,
                            status=TaskStatus(state=TaskState.SUBMITTED),
                            final=False,
                        )
                        yield {
                            "event": "status",
                            "data": initial_event.model_dump_json(),
                        }
                        
                        artifacts = []
                        
                        # Process task and stream updates
                        async for event in self.process_task(
                            task.id,
                            params.message,
                            params.sessionId,
                            params.metadata,
                        ):
                            if isinstance(event, TaskStatusUpdateEvent):
                                # Publish to Redis for other subscribers
                                if self.redis:
                                    await self.redis.publish_status(task.id, event)
                                
                                yield {
                                    "event": "status",
                                    "data": event.model_dump_json(),
                                }
                                
                                # Check if final
                                if event.final or event.status.state in [
                                    TaskState.COMPLETED,
                                    TaskState.FAILED,
                                    TaskState.CANCELED,
                                ]:
                                    break
                                    
                            elif isinstance(event, TaskArtifactUpdateEvent):
                                artifacts.append(event.artifact)
                                
                                if self.redis:
                                    await self.redis.publish_artifact(task.id, event)
                                
                                yield {
                                    "event": "artifact",
                                    "data": event.model_dump_json(),
                                }
                        
                        # Update final task state
                        task.artifacts = artifacts if artifacts else None
                        self.tasks[task.id] = task
                        
                        if self.redis:
                            await self.redis.store_task(task)
                            await self.redis.remove_subscription(task.id, self.agent_card.name)
                            
                    except asyncio.CancelledError:
                        logger.info("SSE connection cancelled", task_id=task.id)
                        raise
                    except Exception as e:
                        logger.error("Error in event generator", error=str(e))
                        error_event = TaskStatusUpdateEvent(
                            id=task.id,
                            status=TaskStatus(
                                state=TaskState.FAILED,
                                message=Message(
                                    role="agent",
                                    parts=[TextPart(text=f"Error: {str(e)}")],
                                ),
                            ),
                            final=True,
                        )
                        yield {
                            "event": "status",
                            "data": error_event.model_dump_json(),
                        }
                
                return EventSourceResponse(event_generator())
                
            except Exception as e:
                logger.error("Error setting up sendSubscribe", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/tasks/resubscribe")
        async def resubscribe(request: Request):
            """
            Resubscribe to an existing task's updates.
            Useful for reconnecting after connection loss.
            """
            body = await request.json()
            logger.info("Received tasks/resubscribe", body=body)
            
            task_id = body.get("params", {}).get("id")
            if not task_id:
                raise HTTPException(status_code=400, detail="Task ID required")
            
            # Check if task exists
            task = self.tasks.get(task_id)
            if not task and self.redis:
                task = await self.redis.get_task(task_id)
            
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            
            async def event_generator():
                """Generate SSE events from Redis subscription."""
                # Send current status first
                yield {
                    "event": "status",
                    "data": TaskStatusUpdateEvent(
                        id=task.id,
                        status=task.status,
                        final=task.status.state in [
                            TaskState.COMPLETED,
                            TaskState.FAILED,
                            TaskState.CANCELED,
                        ],
                    ).model_dump_json(),
                }
                
                # If task is complete, no more updates
                if task.status.state in [
                    TaskState.COMPLETED,
                    TaskState.FAILED,
                    TaskState.CANCELED,
                ]:
                    return
                
                # Subscribe to Redis updates
                if self.redis:
                    async for event in self.redis.subscribe_to_task(task_id):
                        yield event
                        if event.get("event") == "status":
                            data = json.loads(event.get("data", "{}"))
                            if data.get("final"):
                                break
            
            return EventSourceResponse(event_generator())
        
        @app.post("/tasks/get")
        async def get_task(request: Request):
            """Get the current state of a task."""
            body = await request.json()
            task_id = body.get("params", {}).get("id")
            
            if not task_id:
                raise HTTPException(status_code=400, detail="Task ID required")
            
            task = self.tasks.get(task_id)
            if not task and self.redis:
                task = await self.redis.get_task(task_id)
            
            if not task:
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": -32001, "message": "Task not found"},
                }
            
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": task.model_dump(exclude_none=True),
            }
        
        @app.post("/tasks/cancel")
        async def cancel_task(request: Request):
            """Cancel a running task."""
            body = await request.json()
            task_id = body.get("params", {}).get("id")
            
            if not task_id:
                raise HTTPException(status_code=400, detail="Task ID required")
            
            task = self.tasks.get(task_id)
            if task:
                task.status = TaskStatus(state=TaskState.CANCELED)
                self.tasks[task_id] = task
                
                if self.redis:
                    await self.redis.store_task(task)
                    cancel_event = TaskStatusUpdateEvent(
                        id=task_id,
                        status=task.status,
                        final=True,
                    )
                    await self.redis.publish_status(task_id, cancel_event)
            
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"success": True},
            }

