#!/bin/bash

# A2A Customer Service - Local Development Runner
# 
# This script starts all agents locally for development.
# Make sure Redis is running first: docker run -d -p 6379:6379 redis:7-alpine

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       A2A Customer Service - Local Development              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Redis is running
echo -e "${YELLOW}Checking Redis connection...${NC}"
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}Redis is not running!${NC}"
    echo -e "Start Redis with: ${GREEN}docker run -d -p 6379:6379 redis:7-alpine${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Redis is running${NC}"
echo ""

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down agents...${NC}"
    kill $(jobs -p) 2>/dev/null
    echo -e "${GREEN}✓ All agents stopped${NC}"
}

trap cleanup EXIT

# Start agents in background
echo -e "${BLUE}Starting agents...${NC}"
echo ""

# Start Billing Agent
echo -e "${GREEN}Starting Billing Agent on port 8003...${NC}"
python -m agents.billing_agent.main --port 8003 &
BILLING_PID=$!
sleep 1

# Start Booking Agent
echo -e "${GREEN}Starting Booking Agent on port 8002...${NC}"
python -m agents.booking_agent.main --port 8002 &
BOOKING_PID=$!
sleep 1

# Start Intent Agent (with mock detector by default for easy testing)
echo -e "${GREEN}Starting Intent Agent on port 8001...${NC}"
USE_MOCK_DETECTOR=${USE_MOCK_DETECTOR:-true} python -m agents.intent_agent.main --port 8001 &
INTENT_PID=$!
sleep 2

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  All agents are running!                                     ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Intent Agent:  http://localhost:8001                        ║${NC}"
echo -e "${GREEN}║  Booking Agent: http://localhost:8002                        ║${NC}"
echo -e "${GREEN}║  Billing Agent: http://localhost:8003                        ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Agent Cards:                                                ║${NC}"
echo -e "${GREEN}║    curl http://localhost:8001/.well-known/agent.json         ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Demo Clients:                                               ║${NC}"
echo -e "${GREEN}║    CLI:  python -m demo.client                               ║${NC}"
echo -e "${GREEN}║    Web:  python -m demo.web_client                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all agents${NC}"
echo ""

# Wait for all background jobs
wait



