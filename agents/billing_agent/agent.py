"""
Billing Agent A2A Server

Exposes the LangGraph billing workflow via A2A protocol
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

from .graph import get_billing_graph, BillingState


logger = structlog.get_logger()


class BillingAgent(A2AServer):
    """
    Billing Agent - Handles billing operations via LangGraph.
    
    Capabilities:
    - View invoices
    - Process payments
    - Request refunds
    - Check account balance
    - Explain charges
    """
    
    def __init__(
        self,
        redis_manager: Optional[RedisManager] = None,
    ):
        agent_card = AgentCard(
            name="Billing Agent",
            description="Handles billing operations including invoices, payments, and refunds",
            url=os.getenv("BILLING_AGENT_URL", "http://localhost:8003"),
            version="1.0.0",
            capabilities=AgentCapabilities(
                streaming=True,
                pushNotifications=False,
            ),
            skills=[
                AgentSkill(
                    id="view-invoices",
                    name="View Invoices",
                    description="View and explain invoice details",
                    tags=["invoice", "billing", "charges"],
                    examples=[
                        "Show me my invoices",
                        "What is invoice INV5001 for?",
                        "List my pending invoices",
                    ],
                ),
                AgentSkill(
                    id="make-payment",
                    name="Make Payment",
                    description="Process payments for invoices",
                    tags=["payment", "pay", "settle"],
                    examples=[
                        "Pay my invoice INV5002",
                        "I want to pay my bill",
                        "Process payment for $150",
                    ],
                ),
                AgentSkill(
                    id="request-refund",
                    name="Request Refund",
                    description="Request refunds for paid invoices",
                    tags=["refund", "return", "credit"],
                    examples=[
                        "I need a refund for INV5001",
                        "Request refund for incorrect charge",
                    ],
                ),
                AgentSkill(
                    id="check-balance",
                    name="Check Balance",
                    description="View account balance and summary",
                    tags=["balance", "account", "summary"],
                    examples=[
                        "What's my account balance?",
                        "How much do I owe?",
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
        Process a billing request using LangGraph workflow.
        
        Streams status updates as the workflow progresses.
        """
        logger.info("Processing billing task", task_id=task_id)
        
        # Extract text from message
        text = self._extract_text(message)
        if not text:
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="No billing request provided")],
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
                    parts=[TextPart(text="💳 Processing your billing request...")],
                ),
            ),
        )
        
        try:
            # Get the billing graph
            graph = get_billing_graph()
            
            # Initial state
            initial_state: BillingState = {
                "messages": [HumanMessage(content=text)],
                "billing_action": None,
                "billing_details": None,
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
                                        parts=[TextPart(text=f"💳 {status_msg}")],
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
                                            name=f"billing_operation_{artifact_index}",
                                            description="Billing system response",
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
                        name="billing_response",
                        description="Final billing response",
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
                        parts=[TextPart(text="✅ Billing request completed")],
                    ),
                ),
                final=True,
            )
            
        except Exception as e:
            logger.error("Billing task failed", error=str(e), task_id=task_id)
            
            yield TaskStatusUpdateEvent(
                id=task_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text=f"Error processing billing request: {str(e)}")],
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

