"""
CLI Demo Client for A2A Customer Service

Demonstrates the A2A sendSubscribe flow with real-time
status streaming visualization.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
import structlog

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.a2a_client import A2AClient
from common.a2a_protocol import (
    Message,
    TextPart,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TaskState,
)


# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()


class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Background
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_RED = "\033[41m"


def print_header():
    """Print demo header."""
    print(f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗
║       A2A Customer Service - Status Streaming Demo               ║
║                                                                  ║
║  This demo shows real-time status streaming using Google's       ║
║  A2A protocol (sendSubscribe) with SSE.                          ║
╚══════════════════════════════════════════════════════════════════╝{Colors.RESET}
""")


def print_flow_diagram():
    """Print the agent flow diagram."""
    print(f"""
{Colors.DIM}┌─────────────────────────────────────────────────────────────────┐
│                        REQUEST FLOW                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Client ──▶ Intent Agent ──▶ Booking Agent                     │
│      │           │               │                              │
│      │◀──────────│◀──────────────│  (SSE streaming)             │
│                  │                                              │
│                  └──▶ Billing Agent                             │
│                           │                                     │
│      │◀───────────────────│        (SSE streaming)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘{Colors.RESET}
""")


def format_status_event(event: TaskStatusUpdateEvent) -> str:
    """Format a status update event for display."""
    state = event.status.state
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    # State-specific formatting
    state_colors = {
        TaskState.SUBMITTED: (Colors.YELLOW, "📤"),
        TaskState.WORKING: (Colors.BLUE, "⚙️ "),
        TaskState.COMPLETED: (Colors.GREEN, "✅"),
        TaskState.FAILED: (Colors.RED, "❌"),
        TaskState.CANCELED: (Colors.YELLOW, "🚫"),
        TaskState.INPUT_REQUIRED: (Colors.MAGENTA, "❓"),
    }
    
    color, icon = state_colors.get(state, (Colors.WHITE, "•"))
    
    # Extract message text
    msg_text = ""
    if event.status.message and event.status.message.parts:
        for part in event.status.message.parts:
            if hasattr(part, "text"):
                msg_text = part.text
                break
    
    return f"{Colors.DIM}[{timestamp}]{Colors.RESET} {icon} {color}{state.value.upper()}{Colors.RESET}: {msg_text}"


def format_artifact_event(event: TaskArtifactUpdateEvent) -> str:
    """Format an artifact update event for display."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    name = event.artifact.name or "artifact"
    
    # Extract content preview
    content = ""
    for part in event.artifact.parts:
        if hasattr(part, "text"):
            content = part.text[:200]
            if len(part.text) > 200:
                content += "..."
            break
    
    return f"""{Colors.DIM}[{timestamp}]{Colors.RESET} 📦 {Colors.CYAN}ARTIFACT{Colors.RESET}: {name}
{Colors.DIM}└─{Colors.RESET} {content}"""


async def send_request(
    client: A2AClient,
    message_text: str,
) -> None:
    """Send a request and display streaming updates."""
    print(f"\n{Colors.BOLD}Sending request:{Colors.RESET} {message_text}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")
    
    message = Message(
        role="user",
        parts=[TextPart(text=message_text)],
    )
    
    try:
        async for event in client.send_subscribe(message):
            if isinstance(event, TaskStatusUpdateEvent):
                print(format_status_event(event))
            elif isinstance(event, TaskArtifactUpdateEvent):
                print(format_artifact_event(event))
            print()  # Blank line between events
            
    except Exception as e:
        print(f"{Colors.RED}Error: {str(e)}{Colors.RESET}")


async def interactive_mode(client: A2AClient):
    """Run interactive demo mode."""
    print_header()
    print_flow_diagram()
    
    print(f"""
{Colors.BOLD}Sample requests to try:{Colors.RESET}
{Colors.GREEN}Booking:{Colors.RESET}
  • "I'd like to book an appointment for next Monday at 2pm"
  • "Check availability for December 20th"
  • "Cancel my booking BK1001"

{Colors.GREEN}Billing:{Colors.RESET}
  • "Show me my pending invoices"
  • "I need to pay invoice INV5002"
  • "Request a refund for INV5001"

{Colors.DIM}Type 'quit' or 'exit' to stop, 'clear' to clear screen{Colors.RESET}
""")
    
    while True:
        try:
            print(f"\n{Colors.BOLD}{Colors.CYAN}Enter your request:{Colors.RESET}")
            user_input = input("> ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ("quit", "exit", "q"):
                print(f"\n{Colors.GREEN}Goodbye!{Colors.RESET}")
                break
                
            if user_input.lower() == "clear":
                os.system("clear" if os.name == "posix" else "cls")
                print_header()
                continue
                
            await send_request(client, user_input)
            
        except KeyboardInterrupt:
            print(f"\n{Colors.GREEN}Goodbye!{Colors.RESET}")
            break
        except EOFError:
            break


async def demo_mode(client: A2AClient):
    """Run automated demo with sample requests."""
    print_header()
    print_flow_diagram()
    
    demo_requests = [
        ("Booking Request", "I'd like to book an appointment for December 20th at 2pm for a consultation"),
        ("Billing Request", "Show me my pending invoices and total balance"),
        ("General Request", "What services do you offer?"),
    ]
    
    for title, request in demo_requests:
        print(f"\n{Colors.BOLD}{Colors.BG_BLUE} {title} {Colors.RESET}")
        await send_request(client, request)
        print(f"\n{Colors.DIM}{'═' * 60}{Colors.RESET}")
        await asyncio.sleep(2)  # Pause between demos


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="A2A Customer Service Demo Client")
    parser.add_argument(
        "--url",
        type=str,
        default=os.getenv("INTENT_AGENT_URL", "http://localhost:8001"),
        help="Intent Agent URL",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run automated demo instead of interactive mode",
    )
    args = parser.parse_args()
    
    load_dotenv()
    
    async with A2AClient(args.url) as client:
        # Verify connection
        try:
            card = await client.get_agent_card()
            print(f"{Colors.GREEN}✓ Connected to: {card.name}{Colors.RESET}")
            print(f"{Colors.DIM}  URL: {args.url}{Colors.RESET}")
            print(f"{Colors.DIM}  Version: {card.version}{Colors.RESET}")
            print(f"{Colors.DIM}  Streaming: {card.capabilities.streaming}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Could not connect to Intent Agent at {args.url}{Colors.RESET}")
            print(f"{Colors.DIM}  Error: {str(e)}{Colors.RESET}")
            print(f"\n{Colors.YELLOW}Make sure the agents are running:{Colors.RESET}")
            print(f"  python -m agents.intent_agent.main --port 8001")
            print(f"  python -m agents.booking_agent.main --port 8002")
            print(f"  python -m agents.billing_agent.main --port 8003")
            return
        
        if args.demo:
            await demo_mode(client)
        else:
            await interactive_mode(client)


if __name__ == "__main__":
    asyncio.run(main())

