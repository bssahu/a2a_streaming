"""
Booking Agent LangGraph Implementation

Defines the state machine and workflow for processing booking requests
using LangGraph with Claude 4.5 via Bedrock.
"""

import os
from typing import TypedDict, Annotated, Sequence, Literal, Optional, Any
from datetime import datetime, timedelta
import json
import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_aws import ChatBedrock
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
import structlog


logger = structlog.get_logger()


# =============================================================================
# State Definition
# =============================================================================

class BookingState(TypedDict):
    """State for the booking workflow."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    booking_action: Optional[str]  # create, modify, cancel, check_availability
    booking_details: Optional[dict]
    confirmation: Optional[dict]
    status_updates: Annotated[list[str], operator.add]
    error: Optional[str]


# =============================================================================
# Mock Database (simulates booking system)
# =============================================================================

class MockBookingDB:
    """Simulated booking database for demonstration."""
    
    _bookings = {}
    _counter = 1000
    
    @classmethod
    def create_booking(
        cls,
        customer_name: str,
        date: str,
        time: str,
        service: str,
        notes: str = "",
    ) -> dict:
        """Create a new booking."""
        cls._counter += 1
        booking_id = f"BK{cls._counter}"
        
        booking = {
            "id": booking_id,
            "customer_name": customer_name,
            "date": date,
            "time": time,
            "service": service,
            "notes": notes,
            "status": "confirmed",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        cls._bookings[booking_id] = booking
        return booking
    
    @classmethod
    def get_booking(cls, booking_id: str) -> Optional[dict]:
        """Get a booking by ID."""
        return cls._bookings.get(booking_id)
    
    @classmethod
    def modify_booking(cls, booking_id: str, **updates) -> Optional[dict]:
        """Modify an existing booking."""
        booking = cls._bookings.get(booking_id)
        if booking:
            booking.update(updates)
            booking["modified_at"] = datetime.utcnow().isoformat()
            return booking
        return None
    
    @classmethod
    def cancel_booking(cls, booking_id: str) -> bool:
        """Cancel a booking."""
        booking = cls._bookings.get(booking_id)
        if booking:
            booking["status"] = "cancelled"
            booking["cancelled_at"] = datetime.utcnow().isoformat()
            return True
        return False
    
    @classmethod
    def check_availability(cls, date: str, service: str) -> list[str]:
        """Check available time slots for a date and service."""
        # Simulate available slots
        all_slots = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]
        
        # Remove booked slots
        booked_slots = [
            b["time"] for b in cls._bookings.values()
            if b["date"] == date and b["service"] == service and b["status"] == "confirmed"
        ]
        
        return [slot for slot in all_slots if slot not in booked_slots]


# =============================================================================
# Tools
# =============================================================================

@tool
def create_booking(
    customer_name: str,
    date: str,
    time: str,
    service: str,
    notes: str = "",
) -> str:
    """
    Create a new booking.
    
    Args:
        customer_name: Name of the customer
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format
        service: Type of service (e.g., "consultation", "appointment", "reservation")
        notes: Optional notes for the booking
        
    Returns:
        Booking confirmation details
    """
    booking = MockBookingDB.create_booking(
        customer_name=customer_name,
        date=date,
        time=time,
        service=service,
        notes=notes,
    )
    
    return json.dumps({
        "status": "success",
        "message": f"Booking created successfully",
        "booking": booking,
    })


@tool
def check_availability(date: str, service: str) -> str:
    """
    Check available time slots for a specific date and service.
    
    Args:
        date: Date in YYYY-MM-DD format
        service: Type of service
        
    Returns:
        List of available time slots
    """
    available_slots = MockBookingDB.check_availability(date, service)
    
    return json.dumps({
        "date": date,
        "service": service,
        "available_slots": available_slots,
        "message": f"Found {len(available_slots)} available slots for {date}",
    })


@tool
def modify_booking(
    booking_id: str,
    new_date: str = None,
    new_time: str = None,
    new_notes: str = None,
) -> str:
    """
    Modify an existing booking.
    
    Args:
        booking_id: The booking ID (e.g., BK1001)
        new_date: New date in YYYY-MM-DD format (optional)
        new_time: New time in HH:MM format (optional)
        new_notes: New notes (optional)
        
    Returns:
        Updated booking details
    """
    updates = {}
    if new_date:
        updates["date"] = new_date
    if new_time:
        updates["time"] = new_time
    if new_notes:
        updates["notes"] = new_notes
        
    booking = MockBookingDB.modify_booking(booking_id, **updates)
    
    if booking:
        return json.dumps({
            "status": "success",
            "message": "Booking updated successfully",
            "booking": booking,
        })
    else:
        return json.dumps({
            "status": "error",
            "message": f"Booking {booking_id} not found",
        })


@tool
def cancel_booking(booking_id: str) -> str:
    """
    Cancel a booking.
    
    Args:
        booking_id: The booking ID to cancel
        
    Returns:
        Cancellation confirmation
    """
    success = MockBookingDB.cancel_booking(booking_id)
    
    if success:
        return json.dumps({
            "status": "success",
            "message": f"Booking {booking_id} has been cancelled",
        })
    else:
        return json.dumps({
            "status": "error",
            "message": f"Booking {booking_id} not found",
        })


@tool
def get_booking_details(booking_id: str) -> str:
    """
    Get details of a specific booking.
    
    Args:
        booking_id: The booking ID to look up
        
    Returns:
        Booking details
    """
    booking = MockBookingDB.get_booking(booking_id)
    
    if booking:
        return json.dumps({
            "status": "success",
            "booking": booking,
        })
    else:
        return json.dumps({
            "status": "error",
            "message": f"Booking {booking_id} not found",
        })


# Tool list
BOOKING_TOOLS = [
    create_booking,
    check_availability,
    modify_booking,
    cancel_booking,
    get_booking_details,
]


# =============================================================================
# Graph Nodes
# =============================================================================

def create_booking_graph():
    """Create the LangGraph workflow for booking operations."""
    
    # Initialize LLM
    llm = ChatBedrock(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        model_kwargs={"temperature": 0.1},
    )
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(BOOKING_TOOLS)
    
    # System message
    system_message = SystemMessage(content="""You are a helpful booking assistant. 
Your job is to help customers with booking-related tasks:
- Create new bookings/reservations/appointments
- Check availability for specific dates
- Modify existing bookings
- Cancel bookings
- Look up booking details

Always be polite and confirm details with the customer.
When creating bookings, always confirm the booking details.
Use the available tools to perform booking operations.

For dates, use YYYY-MM-DD format.
For times, use HH:MM format (24-hour).
""")
    
    # Node: Analyze request and decide action
    def analyze_request(state: BookingState) -> BookingState:
        """Analyze the customer request and decide on action."""
        messages = [system_message] + list(state["messages"])
        
        response = llm_with_tools.invoke(messages)
        
        return {
            "messages": [response],
            "status_updates": ["Analyzing your booking request..."],
        }
    
    # Node: Execute tool calls
    tool_node = ToolNode(BOOKING_TOOLS)
    
    def execute_tools(state: BookingState) -> BookingState:
        """Execute any tool calls from the LLM."""
        result = tool_node.invoke(state)
        
        # Extract status message from tool results
        status_msg = "Processing booking operation..."
        if result.get("messages"):
            for msg in result["messages"]:
                if hasattr(msg, "content"):
                    try:
                        data = json.loads(msg.content)
                        if "message" in data:
                            status_msg = data["message"]
                    except:
                        pass
        
        return {
            **result,
            "status_updates": [status_msg],
        }
    
    # Node: Generate final response
    def generate_response(state: BookingState) -> BookingState:
        """Generate the final response to the customer."""
        messages = [system_message] + list(state["messages"])
        
        response = llm.invoke(messages)
        
        return {
            "messages": [response],
            "status_updates": ["Generating response..."],
        }
    
    # Routing function
    def should_continue(state: BookingState) -> Literal["tools", "respond", "end"]:
        """Determine next step based on LLM response."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Check if there are tool calls
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        # Check if this is a final response
        if isinstance(last_message, AIMessage) and not hasattr(last_message, "tool_calls"):
            return "end"
            
        return "respond"
    
    # Build the graph
    workflow = StateGraph(BookingState)
    
    # Add nodes
    workflow.add_node("analyze", analyze_request)
    workflow.add_node("tools", execute_tools)
    workflow.add_node("respond", generate_response)
    
    # Add edges
    workflow.set_entry_point("analyze")
    
    workflow.add_conditional_edges(
        "analyze",
        should_continue,
        {
            "tools": "tools",
            "respond": "respond",
            "end": END,
        },
    )
    
    workflow.add_conditional_edges(
        "tools",
        should_continue,
        {
            "tools": "tools",
            "respond": "respond",
            "end": END,
        },
    )
    
    workflow.add_edge("respond", END)
    
    return workflow.compile()


# Create graph instance
booking_graph = None


def get_booking_graph():
    """Get or create the booking graph."""
    global booking_graph
    if booking_graph is None:
        booking_graph = create_booking_graph()
    return booking_graph

