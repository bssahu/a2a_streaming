"""
Booking Agent A2A Server

Exposes the LangGraph booking workflow via A2A protocol
with status streaming.
"""

import os
from typing import AsyncGenerator, Dict, Optional, Any

from langchain_core.messages import HumanMessage
import structlog

from common.a2a_protocol import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    Artifact,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
from common.a2a_server import A2AServer
from common.redis_manager import RedisManager

from .graph import get_booking_graph, BookingState


logger = structlog.get_logger()


class BookingAgent(A2AServer):
    """
    Booking Agent - Handles booking operations via LangGraph.
    
    Capabilities:
    - Create new bookings
    - Check availability
    - Modify existing bookings
    - Cancel bookings
    - Look up booking details
    """
    
    def __init__(
        self,
        redis_manager: Optional[RedisManager] = None,
    ):
        agent_card = AgentCard(
            name="Booking Agent",
            description="Handles booking operations including reservations, appointments, and scheduling",
            url=os.getenv("BOOKING_AGENT_URL", "http://localhost:8002"),
            version="1.0.0",
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=False,
            ),
            skills=[
                AgentSkill(
                    id="create-booking",
                    name="Create Booking",
                    description="Create new reservations, appointments, or bookings",
                    tags=["booking", "reservation", "scheduling"],
                    examples=[
                        "Book a table for 2 on Friday at 7pm",
                        "Schedule an appointment for next Monday",
                        "Reserve a room for December 15th",
                    ],
                ),
                AgentSkill(
                    id="check-availability",
                    name="Check Availability",
                    description="Check available time slots for a specific date",
                    tags=["availability", "scheduling"],
                    examples=[
                        "What times are available on Saturday?",
                        "Check availability for next week",
                    ],
                ),
                AgentSkill(
                    id="modify-booking",
                    name="Modify Booking",
                    description="Change date, time, or other details of an existing booking",
                    tags=["modify", "reschedule", "change"],
                    examples=[
                        "Change my booking to 3pm",
                        "Reschedule my appointment to Tuesday",
                    ],
                ),
                AgentSkill(
                    id="cancel-booking",
                    name="Cancel Booking",
                    description="Cancel an existing booking",
                    tags=["cancel", "delete"],
                    examples=[
                        "Cancel my reservation",
                        "I need to cancel booking BK1001",
                    ],
                ),
            ],
        )
        
        super().__init__(agent_card, redis_manager)
        
    async def process_task(
        self,
        task_id: str,
        message: Message,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Process a booking request using LangGraph workflow.
        
        Streams status updates as the workflow progresses.
        """
        logger.info("Processing booking task", task_id=task_id)
        
        # Extract text from message
        text = self._extract_text(message)
        if not text:
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="No booking request provided")],
                    ),
                ),
                final=True,
            )
            return
            
        # Initial status
        yield TaskStatusUpdateEvent(
            id=task_id,
            status=TaskStatus(
                state=TaskState.WORKING,
                message=Message(
                    role="agent",
                    parts=[TextPart(text="📅 Processing your booking request...")],
                ),
            ),
        )
        
        try:
            # Get the booking graph
            graph = get_booking_graph()
            
            # Initial state
            initial_state: BookingState = {
                "messages": [HumanMessage(content=text)],
                "booking_action": None,
                "booking_details": None,
                "confirmation": None,
                "status_updates": [],
                "error": None,
            }
            
            # Add intent context if available
            if metadata:
                intent_entities = metadata.get("intent_entities", {})
                if intent_entities:
                    context_msg = f"\n[Context: {intent_entities}]"
                    initial_state["messages"][0].content += context_msg
            
            # Stream through the graph
            artifact_index = 0
            final_response = None
            
            async for state_update in graph.astream(initial_state):
                logger.debug("Graph state update", state=state_update)
                
                # Extract the node name and state
                for node_name, node_state in state_update.items():
                    # Stream status updates
                    if "status_updates" in node_state:
                        for status_msg in node_state["status_updates"]:
                            yield TaskStatusUpdateEvent(
                                id=task_id,
                                status=TaskStatus(
                                    state=TaskState.WORKING,
                                    message=Message(
                                        role="agent",
                                        parts=[TextPart(text=f"📅 {status_msg}")],
                                    ),
                                ),
                            )
                    
                    # Capture final response
                    if "messages" in node_state:
                        for msg in node_state["messages"]:
                            if hasattr(msg, "content") and msg.content:
                                final_response = msg.content
                                
                                # If it's a tool response, stream it as artifact
                                if hasattr(msg, "type") and msg.type == "tool":
                                    yield TaskArtifactUpdateEvent(
                                        id=task_id,
                                        artifact=Artifact(
                                            name=f"booking_operation_{artifact_index}",
                                            description="Booking system response",
                                            parts=[TextPart(text=msg.content)],
                                            index=artifact_index,
                                        ),
                                    )
                                    artifact_index += 1
            
            # Final response artifact
            if final_response:
                yield TaskArtifactUpdateEvent(
                    id=task_id,
                    artifact=Artifact(
                        name="booking_response",
                        description="Final booking response",
                        parts=[TextPart(text=final_response)],
                        index=artifact_index,
                    ),
                )
            
            # Completed status
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.COMPLETED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="✅ Booking request completed")],
                    ),
                ),
                final=True,
            )
            
        except Exception as e:
            logger.error("Booking task failed", error=str(e), task_id=task_id)
            
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text=f"Error processing booking: {str(e)}")],
                    ),
                ),
                final=True,
            )
            
    def _extract_text(self, message: Optional[Message]) -> str:
        """Extract text content from a message."""
        if not message:
            return ""
            
        texts = []
        for part in message.parts:
            if hasattr(part, "text"):
                texts.append(part.text)
        return " ".join(texts)



