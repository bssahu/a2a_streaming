"""
Google A2A Protocol Models

Implements the Agent-to-Agent protocol specification for inter-agent communication
with support for streaming status updates via Server-Sent Events (SSE).

Reference: https://github.com/google/A2A
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from uuid import uuid4


def generate_id() -> str:
    """Generate a unique identifier for tasks and messages."""
    return str(uuid4())


# =============================================================================
# Task States
# =============================================================================

class TaskState(str, Enum):
    """
    Represents the lifecycle states of a task in the A2A protocol.
    """
    SUBMITTED = "submitted"      # Task received but not yet started
    WORKING = "working"          # Agent is actively processing
    INPUT_REQUIRED = "input-required"  # Agent needs additional input
    COMPLETED = "completed"      # Task finished successfully
    FAILED = "failed"           # Task failed with error
    CANCELED = "canceled"       # Task was canceled


# =============================================================================
# Message Parts
# =============================================================================

class TextPart(BaseModel):
    """Text content part of a message."""
    type: str = "text"
    text: str


class FilePart(BaseModel):
    """File content part of a message."""
    type: str = "file"
    file: Dict[str, Any]  # Contains mimeType, name, and either bytes or uri


class DataPart(BaseModel):
    """Structured data part of a message."""
    type: str = "data"
    data: Dict[str, Any]


Part = Union[TextPart, FilePart, DataPart]


# =============================================================================
# Messages
# =============================================================================

class Message(BaseModel):
    """
    A message in the A2A protocol.
    Messages can be from users or agents and contain multiple parts.
    """
    role: str = Field(..., description="Either 'user' or 'agent'")
    parts: List[Part]
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Artifacts
# =============================================================================

class Artifact(BaseModel):
    """
    An artifact produced by an agent during task execution.
    Artifacts can be streamed incrementally using the index and append fields.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    parts: List[Part]
    index: int = 0  # Position in artifact list
    append: bool = False  # If true, append to existing artifact at index
    lastChunk: bool = False  # If true, this is the final chunk
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Task Status
# =============================================================================

class TaskStatus(BaseModel):
    """
    Current status of a task including state and optional message.
    """
    state: TaskState
    message: Optional[Message] = None
    timestamp: Optional[str] = None

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()
        super().__init__(**data)


# =============================================================================
# Task
# =============================================================================

class Task(BaseModel):
    """
    Represents a task in the A2A protocol.
    Tasks contain messages, status, and artifacts produced during execution.
    """
    id: str = Field(default_factory=generate_id)
    sessionId: Optional[str] = None
    status: TaskStatus
    history: Optional[List[Message]] = None
    artifacts: Optional[List[Artifact]] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Agent Capabilities & Skills
# =============================================================================

class AgentCapabilities(BaseModel):
    """
    Capabilities supported by an agent.
    """
    streaming: bool = True  # Supports SSE streaming
    pushNotifications: bool = False  # Supports push notifications
    stateTransitionHistory: bool = False  # Supports state history


class AgentSkill(BaseModel):
    """
    A skill that an agent can perform.
    """
    id: str
    name: str
    description: str
    tags: Optional[List[str]] = None
    examples: Optional[List[str]] = None
    inputModes: Optional[List[str]] = None  # e.g., ["text", "audio"]
    outputModes: Optional[List[str]] = None


class AgentCard(BaseModel):
    """
    Agent Card describing an agent's identity, capabilities, and skills.
    Served at /.well-known/agent.json
    """
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: List[AgentSkill] = Field(default_factory=list)
    defaultInputModes: List[str] = Field(default=["text"])
    defaultOutputModes: List[str] = Field(default=["text"])
    provider: Optional[Dict[str, str]] = None
    documentationUrl: Optional[str] = None
    authentication: Optional[Dict[str, Any]] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class TaskSendParams(BaseModel):
    """Parameters for sending a task."""
    id: str = Field(default_factory=generate_id)
    sessionId: Optional[str] = None
    message: Message
    historyLength: Optional[int] = None
    pushNotification: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class SendTaskRequest(BaseModel):
    """Request to send a new task to an agent."""
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=generate_id)
    method: str = "tasks/send"
    params: TaskSendParams


class SendTaskResponse(BaseModel):
    """Response from sending a task."""
    jsonrpc: str = "2.0"
    id: str
    result: Optional[Task] = None
    error: Optional[Dict[str, Any]] = None


class TaskResubscribeParams(BaseModel):
    """Parameters for resubscribing to a task."""
    id: str  # Task ID to resubscribe to


class ResubscribeRequest(BaseModel):
    """Request to resubscribe to an existing task's updates."""
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=generate_id)
    method: str = "tasks/resubscribe"
    params: TaskResubscribeParams


class GetTaskRequest(BaseModel):
    """Request to get task status."""
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=generate_id)
    method: str = "tasks/get"
    params: Dict[str, str]  # Contains task id


class CancelTaskRequest(BaseModel):
    """Request to cancel a task."""
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=generate_id)
    method: str = "tasks/cancel"
    params: Dict[str, str]  # Contains task id


# =============================================================================
# SSE Event Models
# =============================================================================

class TaskStatusUpdateEvent(BaseModel):
    """
    SSE event for task status updates.
    Sent when task state changes.
    """
    id: str  # Task ID
    status: TaskStatus
    final: bool = False  # If true, no more updates will follow


class TaskArtifactUpdateEvent(BaseModel):
    """
    SSE event for artifact updates.
    Sent when new artifacts are produced or updated.
    """
    id: str  # Task ID
    artifact: Artifact


# =============================================================================
# JSON-RPC Notification for Push
# =============================================================================

class TaskStatusNotification(BaseModel):
    """Push notification for task status updates."""
    jsonrpc: str = "2.0"
    method: str = "tasks/status"
    params: Dict[str, Any]  # Contains taskId and status


class TaskArtifactNotification(BaseModel):
    """Push notification for artifact updates."""
    jsonrpc: str = "2.0"
    method: str = "tasks/artifact"
    params: Dict[str, Any]  # Contains taskId and artifact

