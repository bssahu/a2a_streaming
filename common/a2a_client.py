"""
A2A Client Implementation

Client for communicating with A2A-compliant agents,
supporting both synchronous and streaming (SSE) communication.
"""

import asyncio
import json
from typing import AsyncGenerator, Dict, Optional, Any

import httpx
from httpx_sse import aconnect_sse
import structlog

from .a2a_protocol import (
    AgentCard,
    Task,
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    TaskSendParams,
    SendTaskRequest,
    SendTaskResponse,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    generate_id,
)


logger = structlog.get_logger()


class A2AClient:
    """
    Client for communicating with A2A-compliant agents.
    
    Supports:
    - Fetching agent cards
    - Sending tasks (synchronous)
    - Sending tasks with streaming (sendSubscribe)
    - Resubscribing to tasks
    - Getting task status
    - Canceling tasks
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        
    async def connect(self):
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers=self.headers,
        )
        
    async def disconnect(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            
    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first or use async context manager.")
        return self._client
    
    async def get_agent_card(self) -> AgentCard:
        """Fetch the agent card from the server."""
        response = await self.client.get(f"{self.base_url}/.well-known/agent.json")
        response.raise_for_status()
        return AgentCard(**response.json())
    
    async def send_task(
        self,
        message: Message,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        Send a task and wait for completion (non-streaming).
        
        Args:
            message: The message to send
            task_id: Optional task ID (generated if not provided)
            session_id: Optional session ID for conversation context
            metadata: Optional metadata for the task
            
        Returns:
            The completed Task object
        """
        request = SendTaskRequest(
            params=TaskSendParams(
                id=task_id or generate_id(),
                sessionId=session_id,
                message=message,
                metadata=metadata,
            ),
        )
        
        response = await self.client.post(
            f"{self.base_url}/tasks/send",
            json=request.model_dump(exclude_none=True),
        )
        response.raise_for_status()
        
        result = SendTaskResponse(**response.json())
        if result.error:
            raise Exception(f"Task error: {result.error}")
        
        return result.result
    
    async def send_subscribe(
        self,
        message: Message,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Send a task with SSE streaming for real-time updates.
        
        This is the primary method for A2A communication with status streaming.
        Uses tasks/sendSubscribe endpoint.
        
        Args:
            message: The message to send
            task_id: Optional task ID (generated if not provided)
            session_id: Optional session ID for conversation context
            metadata: Optional metadata for the task
            
        Yields:
            TaskStatusUpdateEvent or TaskArtifactUpdateEvent objects
        """
        request = SendTaskRequest(
            method="tasks/sendSubscribe",
            params=TaskSendParams(
                id=task_id or generate_id(),
                sessionId=session_id,
                message=message,
                metadata=metadata,
            ),
        )
        
        logger.info(
            "Sending sendSubscribe request",
            url=f"{self.base_url}/tasks/sendSubscribe",
            task_id=request.params.id,
        )
        
        async with aconnect_sse(
            self.client,
            "POST",
            f"{self.base_url}/tasks/sendSubscribe",
            json=request.model_dump(exclude_none=True),
        ) as event_source:
            async for event in event_source.aiter_sse():
                logger.debug("Received SSE event", event_type=event.event, data=event.data)
                
                if event.event == "status":
                    data = json.loads(event.data)
                    yield TaskStatusUpdateEvent(**data)
                    
                    # Check for terminal state
                    if data.get("final") or data.get("status", {}).get("state") in [
                        "completed", "failed", "canceled"
                    ]:
                        break
                        
                elif event.event == "artifact":
                    data = json.loads(event.data)
                    yield TaskArtifactUpdateEvent(**data)
    
    async def resubscribe(
        self,
        task_id: str,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Resubscribe to an existing task's updates.
        
        Useful for reconnecting after connection loss.
        
        Args:
            task_id: The ID of the task to resubscribe to
            
        Yields:
            TaskStatusUpdateEvent or TaskArtifactUpdateEvent objects
        """
        request = {
            "jsonrpc": "2.0",
            "id": generate_id(),
            "method": "tasks/resubscribe",
            "params": {"id": task_id},
        }
        
        async with aconnect_sse(
            self.client,
            "POST",
            f"{self.base_url}/tasks/resubscribe",
            json=request,
        ) as event_source:
            async for event in event_source.aiter_sse():
                if event.event == "status":
                    data = json.loads(event.data)
                    yield TaskStatusUpdateEvent(**data)
                    
                    if data.get("final"):
                        break
                        
                elif event.event == "artifact":
                    data = json.loads(event.data)
                    yield TaskArtifactUpdateEvent(**data)
    
    async def get_task(self, task_id: str) -> Task:
        """
        Get the current state of a task.
        
        Args:
            task_id: The ID of the task to get
            
        Returns:
            The Task object
        """
        request = {
            "jsonrpc": "2.0",
            "id": generate_id(),
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        
        response = await self.client.post(
            f"{self.base_url}/tasks/get",
            json=request,
        )
        response.raise_for_status()
        
        result = response.json()
        if result.get("error"):
            raise Exception(f"Task error: {result['error']}")
        
        return Task(**result["result"])
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.
        
        Args:
            task_id: The ID of the task to cancel
            
        Returns:
            True if cancellation was successful
        """
        request = {
            "jsonrpc": "2.0",
            "id": generate_id(),
            "method": "tasks/cancel",
            "params": {"id": task_id},
        }
        
        response = await self.client.post(
            f"{self.base_url}/tasks/cancel",
            json=request,
        )
        response.raise_for_status()
        
        result = response.json()
        return result.get("result", {}).get("success", False)


class MultiAgentClient:
    """
    Client for managing connections to multiple A2A agents.
    
    Useful for the Intent Agent to route requests to different
    downstream agents (Booking, Billing, etc.).
    """
    
    def __init__(self):
        self.agents: Dict[str, A2AClient] = {}
        
    async def register_agent(
        self,
        name: str,
        url: str,
        timeout: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Register a new agent connection."""
        client = A2AClient(url, timeout, headers)
        await client.connect()
        self.agents[name] = client
        logger.info("Registered agent", name=name, url=url)
        
    async def disconnect_all(self):
        """Disconnect from all agents."""
        for name, client in self.agents.items():
            await client.disconnect()
            logger.info("Disconnected from agent", name=name)
        self.agents.clear()
        
    def get_client(self, name: str) -> A2AClient:
        """Get a client by agent name."""
        if name not in self.agents:
            raise KeyError(f"Agent '{name}' not registered")
        return self.agents[name]
    
    async def forward_with_streaming(
        self,
        agent_name: str,
        message: Message,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Forward a request to an agent and stream responses.
        
        This is the primary method for routing requests with
        status streaming intact.
        """
        client = self.get_client(agent_name)
        
        async for event in client.send_subscribe(
            message=message,
            task_id=task_id,
            session_id=session_id,
            metadata=metadata,
        ):
            yield event



