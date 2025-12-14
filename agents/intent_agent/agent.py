"""
Intent Agent Implementation

Entry point for the customer service system. Receives customer requests,
detects intent using Claude 4.5, and routes to appropriate downstream
agents with status streaming.
"""

import os
from typing import AsyncGenerator, Dict, Optional, Any

import structlog

from common.a2a_protocol import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Task,
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    Artifact,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
from common.a2a_server import A2AServer
from common.a2a_client import MultiAgentClient
from common.redis_manager import RedisManager

from .intent_detector import IntentDetector, IntentDetectorMock, Intent, IntentResult


logger = structlog.get_logger()


class IntentAgent(A2AServer):
    """
    Intent Agent - Entry point for customer service.
    
    Flow:
    1. Receive customer request via sendSubscribe
    2. Stream "working" status immediately
    3. Detect intent using Claude 4.5 (Bedrock)
    4. Stream intent detection result as artifact
    5. Route to appropriate agent (booking/billing)
    6. Forward streaming responses back to client
    7. Stream final "completed" status
    """
    
    def __init__(
        self,
        redis_manager: Optional[RedisManager] = None,
        use_mock_detector: bool = False,
    ):
        # Configure agent card
        agent_card = AgentCard(
            name="Intent Agent",
            description="Customer service entry point with intelligent intent detection and routing",
            url=os.getenv("INTENT_AGENT_URL", "http://localhost:8001"),
            version="1.0.0",
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=False,
            ),
            skills=[
                AgentSkill(
                    id="intent-detection",
                    name="Intent Detection",
                    description="Analyzes customer messages to determine intent (booking, billing, general)",
                    tags=["nlp", "classification", "routing"],
                    examples=[
                        "I need to book a hotel room for next week",
                        "Can you send me my invoice from last month?",
                        "I want to cancel my reservation",
                    ],
                ),
                AgentSkill(
                    id="request-routing",
                    name="Request Routing",
                    description="Routes requests to specialized agents (booking, billing)",
                    tags=["routing", "orchestration"],
                ),
            ],
        )
        
        super().__init__(agent_card, redis_manager)
        
        # Initialize intent detector
        if use_mock_detector:
            self.detector = IntentDetectorMock()
            logger.info("Using mock intent detector")
        else:
            self.detector = IntentDetector(
                region=os.getenv("AWS_REGION", "us-east-1"),
            )
            
        # Multi-agent client for routing
        self.downstream_agents = MultiAgentClient()
        
    async def register_downstream_agents(self):
        """Register connections to downstream agents."""
        booking_url = os.getenv("BOOKING_AGENT_URL", "http://localhost:8002")
        billing_url = os.getenv("BILLING_AGENT_URL", "http://localhost:8003")
        
        await self.downstream_agents.register_agent("booking", booking_url)
        await self.downstream_agents.register_agent("billing", billing_url)
        
        logger.info(
            "Registered downstream agents",
            booking=booking_url,
            billing=billing_url,
        )
        
    async def process_task(
        self,
        task_id: str,
        message: Message,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Process a customer request with intent detection and routing.
        
        Yields status updates and artifacts throughout the process.
        """
        logger.info("Processing task", task_id=task_id)
        
        # Extract text from message
        text = self._extract_text(message)
        if not text:
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="No text content in message")],
                    ),
                ),
                final=True,
            )
            return
            
        # =====================================================================
        # Step 1: Intent Detection
        # =====================================================================
        
        yield TaskStatusUpdateEvent(
            id=task_id,
            status=TaskStatus(
                state=TaskState.WORKING,
                message=Message(
                    role="agent",
                    parts=[TextPart(text="🔍 Analyzing your request...")],
                ),
            ),
        )
        
        # Detect intent
        intent_result = await self.detector.detect(text)
        
        # Yield intent detection result as artifact
        yield TaskArtifactUpdateEvent(
            id=task_id,
            artifact=Artifact(
                name="intent_detection",
                description="Intent classification result",
                parts=[
                    TextPart(
                        text=f"Intent: {intent_result.intent.value}\n"
                             f"Confidence: {intent_result.confidence:.2f}\n"
                             f"Reasoning: {intent_result.reasoning}"
                    ),
                ],
                index=0,
                metadata={
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                    "entities": intent_result.extracted_entities,
                },
            ),
        )
        
        # =====================================================================
        # Step 2: Route to appropriate agent
        # =====================================================================
        
        if intent_result.intent == Intent.BOOKING:
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.WORKING,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="📅 Routing to Booking Agent...")],
                    ),
                ),
            )
            
            # Forward to booking agent and stream responses
            async for event in self._forward_to_agent(
                "booking",
                task_id,
                message,
                session_id,
                metadata,
                intent_result,
            ):
                yield event
                
        elif intent_result.intent == Intent.BILLING:
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.WORKING,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="💳 Routing to Billing Agent...")],
                    ),
                ),
            )
            
            # Forward to billing agent and stream responses
            async for event in self._forward_to_agent(
                "billing",
                task_id,
                message,
                session_id,
                metadata,
                intent_result,
            ):
                yield event
                
        else:
            # Handle general inquiries locally
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.WORKING,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="💬 Processing general inquiry...")],
                    ),
                ),
            )
            
            # Generate response for general inquiry
            yield TaskArtifactUpdateEvent(
                id=task_id,
                artifact=Artifact(
                    name="response",
                    description="Response to general inquiry",
                    parts=[
                        TextPart(
                            text="Thank you for your message. For booking-related requests "
                                 "(reservations, appointments, scheduling), I'll route you to our "
                                 "Booking team. For billing questions (invoices, payments, refunds), "
                                 "I'll connect you with our Billing team. How can I help you today?"
                        ),
                    ],
                    index=1,
                ),
            )
            
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.COMPLETED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="✅ Request processed")],
                    ),
                ),
                final=True,
            )
            
    async def _forward_to_agent(
        self,
        agent_name: str,
        task_id: str,
        message: Message,
        session_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
        intent_result: IntentResult,
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        """
        Forward request to a downstream agent and stream responses.
        
        Transforms events to maintain the original task_id.
        """
        try:
            # Add intent context to metadata
            enriched_metadata = {
                **(metadata or {}),
                "intent": intent_result.intent.value,
                "intent_confidence": intent_result.confidence,
                "intent_entities": intent_result.extracted_entities,
                "source_agent": "intent_agent",
            }
            
            artifact_index = 2  # Start after intent detection artifact
            
            async for event in self.downstream_agents.forward_with_streaming(
                agent_name=agent_name,
                message=message,
                session_id=session_id,
                metadata=enriched_metadata,
            ):
                if isinstance(event, TaskStatusUpdateEvent):
                    # Transform to use original task ID and add agent source
                    transformed_status = TaskStatusUpdateEvent(
                        id=task_id,
                        status=TaskStatus(
                            state=event.status.state,
                            message=Message(
                                role="agent",
                                parts=[
                                    TextPart(
                                        text=f"[{agent_name.title()}] "
                                             f"{self._extract_text(event.status.message) if event.status.message else event.status.state}"
                                    ),
                                ],
                            ) if event.status.message else event.status.message,
                        ),
                        final=event.final,
                    )
                    yield transformed_status
                    
                elif isinstance(event, TaskArtifactUpdateEvent):
                    # Transform artifact with correct task ID and index
                    transformed_artifact = TaskArtifactUpdateEvent(
                        id=task_id,
                        artifact=Artifact(
                            name=f"{agent_name}_{event.artifact.name or 'result'}",
                            description=event.artifact.description,
                            parts=event.artifact.parts,
                            index=artifact_index,
                            metadata={
                                **(event.artifact.metadata or {}),
                                "source_agent": agent_name,
                            },
                        ),
                    )
                    artifact_index += 1
                    yield transformed_artifact
                    
        except Exception as e:
            logger.error(
                "Error forwarding to agent",
                agent=agent_name,
                error=str(e),
            )
            
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text=f"Error connecting to {agent_name} agent: {str(e)}")],
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



