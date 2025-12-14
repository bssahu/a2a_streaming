"""
Billing Agent Main Entry Point

Starts the Billing Agent server with A2A protocol support.
"""

import os

import uvicorn
from dotenv import load_dotenv
import structlog

from common.redis_manager import RedisManager
from .agent import BillingAgent


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def create_app():
    """Create the Billing Agent FastAPI application."""
    load_dotenv()
    
    # Initialize Redis manager
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_manager = RedisManager(url=redis_url)
    
    # Create agent
    agent = BillingAgent(redis_manager=redis_manager)
    
    # Create FastAPI app
    app = agent.create_app()
    
    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Billing Agent Server")
    parser.add_argument("--port", type=int, default=8003, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()
    
    logger.info("Starting Billing Agent", port=args.port, host=args.host)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )



