"""
Billing Agent LangGraph Implementation

Defines the state machine and workflow for processing billing requests
using LangGraph with Claude 4.5 via Bedrock.
"""

import os
from typing import TypedDict, Annotated, Sequence, Literal, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import json
import operator
import random

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

class BillingState(TypedDict):
    """State for the billing workflow."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    billing_action: Optional[str]  # view_invoice, make_payment, request_refund, check_balance
    billing_details: Optional[dict]
    confirmation: Optional[dict]
    status_updates: Annotated[list[str], operator.add]
    error: Optional[str]


# =============================================================================
# Mock Database (simulates billing system)
# =============================================================================

class MockBillingDB:
    """Simulated billing database for demonstration."""
    
    _invoices = {}
    _payments = {}
    _accounts = {}
    _counter = 5000
    
    @classmethod
    def _ensure_demo_data(cls):
        """Ensure demo data exists."""
        if not cls._invoices:
            # Create some demo invoices
            cls._invoices = {
                "INV5001": {
                    "id": "INV5001",
                    "customer_id": "CUST001",
                    "amount": 150.00,
                    "description": "Monthly subscription - December 2024",
                    "status": "paid",
                    "due_date": "2024-12-15",
                    "paid_date": "2024-12-10",
                    "created_at": "2024-12-01T00:00:00",
                },
                "INV5002": {
                    "id": "INV5002",
                    "customer_id": "CUST001",
                    "amount": 275.50,
                    "description": "Service charges - Q4 2024",
                    "status": "pending",
                    "due_date": "2024-12-31",
                    "created_at": "2024-12-15T00:00:00",
                },
                "INV5003": {
                    "id": "INV5003",
                    "customer_id": "CUST001",
                    "amount": 50.00,
                    "description": "Late payment fee",
                    "status": "overdue",
                    "due_date": "2024-11-30",
                    "created_at": "2024-11-15T00:00:00",
                },
            }
            
            cls._accounts["CUST001"] = {
                "customer_id": "CUST001",
                "name": "Demo Customer",
                "balance": 325.50,  # Amount due
                "credit": 0.00,
                "payment_method": "card_ending_4242",
            }
    
    @classmethod
    def get_invoice(cls, invoice_id: str) -> Optional[dict]:
        """Get an invoice by ID."""
        cls._ensure_demo_data()
        return cls._invoices.get(invoice_id)
    
    @classmethod
    def list_invoices(cls, customer_id: str = "CUST001", status: str = None) -> list[dict]:
        """List invoices for a customer."""
        cls._ensure_demo_data()
        invoices = [
            inv for inv in cls._invoices.values()
            if inv["customer_id"] == customer_id
        ]
        if status:
            invoices = [inv for inv in invoices if inv["status"] == status]
        return invoices
    
    @classmethod
    def make_payment(
        cls,
        invoice_id: str,
        amount: float,
        payment_method: str = "default",
    ) -> dict:
        """Process a payment for an invoice."""
        cls._ensure_demo_data()
        
        invoice = cls._invoices.get(invoice_id)
        if not invoice:
            return {"status": "error", "message": f"Invoice {invoice_id} not found"}
        
        if invoice["status"] == "paid":
            return {"status": "error", "message": f"Invoice {invoice_id} is already paid"}
        
        if amount < invoice["amount"]:
            return {"status": "error", "message": f"Payment amount ${amount} is less than invoice amount ${invoice['amount']}"}
        
        cls._counter += 1
        payment_id = f"PAY{cls._counter}"
        
        payment = {
            "id": payment_id,
            "invoice_id": invoice_id,
            "amount": amount,
            "payment_method": payment_method,
            "status": "completed",
            "processed_at": datetime.utcnow().isoformat(),
        }
        
        cls._payments[payment_id] = payment
        
        # Update invoice
        invoice["status"] = "paid"
        invoice["paid_date"] = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Update account balance
        account = cls._accounts.get(invoice["customer_id"])
        if account:
            account["balance"] = max(0, account["balance"] - amount)
        
        return {
            "status": "success",
            "payment": payment,
            "message": f"Payment of ${amount} processed successfully for invoice {invoice_id}",
        }
    
    @classmethod
    def request_refund(
        cls,
        invoice_id: str,
        reason: str,
        amount: float = None,
    ) -> dict:
        """Request a refund for a paid invoice."""
        cls._ensure_demo_data()
        
        invoice = cls._invoices.get(invoice_id)
        if not invoice:
            return {"status": "error", "message": f"Invoice {invoice_id} not found"}
        
        if invoice["status"] != "paid":
            return {"status": "error", "message": f"Invoice {invoice_id} is not paid. Cannot refund."}
        
        refund_amount = amount or invoice["amount"]
        
        cls._counter += 1
        refund_id = f"REF{cls._counter}"
        
        refund = {
            "id": refund_id,
            "invoice_id": invoice_id,
            "amount": refund_amount,
            "reason": reason,
            "status": "pending_review",
            "requested_at": datetime.utcnow().isoformat(),
            "estimated_processing": "3-5 business days",
        }
        
        return {
            "status": "success",
            "refund": refund,
            "message": f"Refund request submitted for ${refund_amount}. Reference: {refund_id}",
        }
    
    @classmethod
    def get_account_balance(cls, customer_id: str = "CUST001") -> dict:
        """Get account balance and summary."""
        cls._ensure_demo_data()
        
        account = cls._accounts.get(customer_id)
        if not account:
            return {"status": "error", "message": "Account not found"}
        
        invoices = cls.list_invoices(customer_id)
        pending = sum(inv["amount"] for inv in invoices if inv["status"] == "pending")
        overdue = sum(inv["amount"] for inv in invoices if inv["status"] == "overdue")
        
        return {
            "status": "success",
            "account": {
                **account,
                "pending_amount": pending,
                "overdue_amount": overdue,
                "total_due": pending + overdue,
            },
        }


# =============================================================================
# Tools
# =============================================================================

@tool
def get_invoice(invoice_id: str) -> str:
    """
    Get details of a specific invoice.
    
    Args:
        invoice_id: The invoice ID (e.g., INV5001)
        
    Returns:
        Invoice details
    """
    invoice = MockBillingDB.get_invoice(invoice_id)
    
    if invoice:
        return json.dumps({
            "status": "success",
            "invoice": invoice,
        })
    else:
        return json.dumps({
            "status": "error",
            "message": f"Invoice {invoice_id} not found",
        })


@tool
def list_invoices(status: str = None) -> str:
    """
    List all invoices. Optionally filter by status.
    
    Args:
        status: Filter by status (paid, pending, overdue). Optional.
        
    Returns:
        List of invoices
    """
    invoices = MockBillingDB.list_invoices(status=status)
    
    return json.dumps({
        "status": "success",
        "count": len(invoices),
        "invoices": invoices,
    })


@tool
def make_payment(
    invoice_id: str,
    amount: float,
    payment_method: str = "default",
) -> str:
    """
    Make a payment for an invoice.
    
    Args:
        invoice_id: The invoice ID to pay
        amount: Payment amount
        payment_method: Payment method (default uses card on file)
        
    Returns:
        Payment confirmation
    """
    result = MockBillingDB.make_payment(invoice_id, amount, payment_method)
    return json.dumps(result)


@tool
def request_refund(
    invoice_id: str,
    reason: str,
    amount: float = None,
) -> str:
    """
    Request a refund for a paid invoice.
    
    Args:
        invoice_id: The invoice ID to refund
        reason: Reason for the refund request
        amount: Refund amount (defaults to full invoice amount)
        
    Returns:
        Refund request confirmation
    """
    result = MockBillingDB.request_refund(invoice_id, reason, amount)
    return json.dumps(result)


@tool
def get_account_balance() -> str:
    """
    Get the current account balance and summary.
    
    Returns:
        Account balance and payment summary
    """
    result = MockBillingDB.get_account_balance()
    return json.dumps(result)


# Tool list
BILLING_TOOLS = [
    get_invoice,
    list_invoices,
    make_payment,
    request_refund,
    get_account_balance,
]


# =============================================================================
# Graph Nodes
# =============================================================================

def create_billing_graph():
    """Create the LangGraph workflow for billing operations."""
    
    # Initialize LLM
    llm = ChatBedrock(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        model_kwargs={"temperature": 0.1},
    )
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(BILLING_TOOLS)
    
    # System message
    system_message = SystemMessage(content="""You are a helpful billing assistant.
Your job is to help customers with billing-related tasks:
- View and explain invoices
- Process payments
- Request refunds
- Check account balance
- Answer questions about charges

Always be polite and explain charges clearly.
When processing payments, confirm the amount before proceeding.
For refunds, always ask for a reason if not provided.

Format currency as $X.XX (e.g., $150.00).
""")
    
    # Node: Analyze request and decide action
    def analyze_request(state: BillingState) -> BillingState:
        """Analyze the customer request and decide on action."""
        messages = [system_message] + list(state["messages"])
        
        response = llm_with_tools.invoke(messages)
        
        return {
            "messages": [response],
            "status_updates": ["Analyzing your billing request..."],
        }
    
    # Node: Execute tool calls
    tool_node = ToolNode(BILLING_TOOLS)
    
    def execute_tools(state: BillingState) -> BillingState:
        """Execute any tool calls from the LLM."""
        result = tool_node.invoke(state)
        
        # Extract status message from tool results
        status_msg = "Processing billing operation..."
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
    def generate_response(state: BillingState) -> BillingState:
        """Generate the final response to the customer."""
        messages = [system_message] + list(state["messages"])
        
        response = llm.invoke(messages)
        
        return {
            "messages": [response],
            "status_updates": ["Generating response..."],
        }
    
    # Routing function
    def should_continue(state: BillingState) -> Literal["tools", "respond", "end"]:
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
    workflow = StateGraph(BillingState)
    
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
billing_graph = None


def get_billing_graph():
    """Get or create the billing graph."""
    global billing_graph
    if billing_graph is None:
        billing_graph = create_billing_graph()
    return billing_graph



