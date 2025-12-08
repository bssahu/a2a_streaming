"""
Intent Agent Main Entry Point

Starts the Intent Agent server with A2A protocol support.
"""

import os
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
import structlog

from common.redis_manager import RedisManager
from .agent import IntentAgent


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


def create_app(use_mock: bool = False):
    """Create the Intent Agent FastAPI application."""
    load_dotenv()
    
    # Initialize Redis manager
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_manager = RedisManager(url=redis_url)
    
    # Create agent
    agent = IntentAgent(
        redis_manager=redis_manager,
        use_mock_detector=use_mock,
    )
    
    # Create FastAPI app with custom lifespan
    app = agent.create_app()
    
    # Store agent reference for lifespan access
    app.state.agent = agent
    
    # Override lifespan to include downstream agent registration
    original_lifespan = app.router.lifespan_context
    
    @asynccontextmanager
    async def custom_lifespan(app):
        # Connect to Redis
        await redis_manager.connect()
        logger.info("Redis connected")
        
        # Register downstream agents
        try:
            await agent.register_downstream_agents()
        except Exception as e:
            logger.warning("Could not register downstream agents", error=str(e))
            logger.info("Intent Agent will operate in standalone mode")
        
        yield
        
        # Cleanup
        await agent.downstream_agents.disconnect_all()
        await redis_manager.disconnect()
        
    app.router.lifespan_context = custom_lifespan
    
    return app


# Create default app instance
app = create_app(use_mock=os.getenv("USE_MOCK_DETECTOR", "false").lower() == "true")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Intent Agent Server")
    parser.add_argument("--port", type=int, default=8001, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--mock", action="store_true", help="Use mock intent detector")
    args = parser.parse_args()
    
    if args.mock:
        app = create_app(use_mock=True)
    
    logger.info("Starting Intent Agent", port=args.port, host=args.host)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )

