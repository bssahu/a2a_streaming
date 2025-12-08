"""
Tests for A2A protocol models.
"""

import pytest
from common.a2a_protocol import (
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    Task,
    Artifact,
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    generate_id,
)


class TestTaskState:
    """Tests for TaskState enum."""
    
    def test_task_states_exist(self):
        """Verify all expected task states exist."""
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.WORKING == "working"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELED == "canceled"
        assert TaskState.INPUT_REQUIRED == "input-required"


class TestMessage:
    """Tests for Message model."""
    
    def test_create_user_message(self):
        """Test creating a user message."""
        msg = Message(
            role="user",
            parts=[TextPart(text="Hello, world!")],
        )
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0].text == "Hello, world!"
    
    def test_create_agent_message(self):
        """Test creating an agent message."""
        msg = Message(
            role="agent",
            parts=[TextPart(text="How can I help you?")],
        )
        assert msg.role == "agent"
    
    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = Message(
            role="user",
            parts=[TextPart(text="Test")],
            metadata={"source": "web", "session_id": "123"},
        )
        assert msg.metadata["source"] == "web"


class TestTask:
    """Tests for Task model."""
    
    def test_create_task(self):
        """Test creating a task."""
        task = Task(
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        assert task.id is not None
        assert task.status.state == TaskState.SUBMITTED
    
    def test_task_with_history(self):
        """Test task with message history."""
        msg = Message(role="user", parts=[TextPart(text="Hello")])
        task = Task(
            status=TaskStatus(state=TaskState.WORKING),
            history=[msg],
        )
        assert len(task.history) == 1
        assert task.history[0].parts[0].text == "Hello"
    
    def test_task_with_artifacts(self):
        """Test task with artifacts."""
        artifact = Artifact(
            name="result",
            parts=[TextPart(text="Result data")],
        )
        task = Task(
            status=TaskStatus(state=TaskState.COMPLETED),
            artifacts=[artifact],
        )
        assert len(task.artifacts) == 1
        assert task.artifacts[0].name == "result"


class TestAgentCard:
    """Tests for AgentCard model."""
    
    def test_create_agent_card(self):
        """Test creating an agent card."""
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8000",
        )
        assert card.name == "Test Agent"
        assert card.capabilities.streaming is True  # Default
        assert card.version == "1.0.0"  # Default
    
    def test_agent_card_with_skills(self):
        """Test agent card with skills."""
        skill = AgentSkill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            tags=["test", "demo"],
        )
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8000",
            skills=[skill],
        )
        assert len(card.skills) == 1
        assert card.skills[0].id == "test-skill"


class TestTaskStatusUpdateEvent:
    """Tests for TaskStatusUpdateEvent model."""
    
    def test_create_status_event(self):
        """Test creating a status update event."""
        event = TaskStatusUpdateEvent(
            id="task-123",
            status=TaskStatus(state=TaskState.WORKING),
        )
        assert event.id == "task-123"
        assert event.status.state == TaskState.WORKING
        assert event.final is False
    
    def test_final_status_event(self):
        """Test creating a final status event."""
        event = TaskStatusUpdateEvent(
            id="task-123",
            status=TaskStatus(state=TaskState.COMPLETED),
            final=True,
        )
        assert event.final is True


class TestTaskArtifactUpdateEvent:
    """Tests for TaskArtifactUpdateEvent model."""
    
    def test_create_artifact_event(self):
        """Test creating an artifact update event."""
        artifact = Artifact(
            name="test-artifact",
            parts=[TextPart(text="Artifact content")],
            index=0,
        )
        event = TaskArtifactUpdateEvent(
            id="task-123",
            artifact=artifact,
        )
        assert event.id == "task-123"
        assert event.artifact.name == "test-artifact"


class TestGenerateId:
    """Tests for ID generation."""
    
    def test_generate_id_is_unique(self):
        """Test that generated IDs are unique."""
        ids = [generate_id() for _ in range(100)]
        assert len(ids) == len(set(ids))
    
    def test_generate_id_is_string(self):
        """Test that generated ID is a string."""
        id = generate_id()
        assert isinstance(id, str)
        assert len(id) > 0

