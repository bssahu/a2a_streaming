# A2A Customer Service Platform

[![CI](https://github.com/bssahu/a2a_streaming/actions/workflows/ci.yml/badge.svg)](https://github.com/bssahu/a2a_streaming/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A distributed customer service solution powered by **Google's Agent-to-Agent (A2A) protocol** with real-time status streaming via Server-Sent Events (SSE).

## ✨ Features

- **🔄 A2A Protocol Compliance** - Full implementation of Google's Agent-to-Agent protocol
- **📡 Real-time Streaming** - SSE-based status updates via `sendSubscribe`
- **🧠 Intent Detection** - Claude 4.5 (via AWS Bedrock) for intelligent request routing
- **🔀 LangGraph Agents** - Sophisticated booking and billing workflows with state machines
- **💾 Redis-backed State** - Distributed subscription and status management
- **☸️ Kubernetes Ready** - Independent pod deployment with auto-scaling

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Customer Request                                    │
│                                    │                                             │
│                                    ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         INTENT AGENT (Entry Point)                       │    │
│  │  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐      │    │
│  │  │ A2A Server  │───▶│ Claude 4.5       │───▶│ Intent Router      │      │    │
│  │  │ /sendSubscribe│   │ (Bedrock)        │    │ (booking/billing)  │      │    │
│  │  └─────────────┘    └──────────────────┘    └────────────────────┘      │    │
│  └──────────────────────────────────┬──────────────────────────────────────┘    │
│                                     │                                            │
│                    ┌────────────────┼────────────────┐                          │
│                    │                │                │                          │
│                    ▼                ▼                ▼                          │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐        │
│  │   BOOKING AGENT    │  │   BILLING AGENT    │  │   [Future Agents]  │        │
│  │   (LangGraph)      │  │   (LangGraph)      │  │                    │        │
│  │   - Reservations   │  │   - Invoices       │  │                    │        │
│  │   - Availability   │  │   - Payments       │  │                    │        │
│  │   - Modifications  │  │   - Refunds        │  │                    │        │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘        │
│           │                       │                                             │
│           └───────────┬───────────┘                                             │
│                       ▼                                                         │
│           ┌────────────────────┐                                                │
│           │       REDIS        │                                                │
│           │  - Pub/Sub Status  │                                                │
│           │  - Task State      │                                                │
│           │  - Subscriptions   │                                                │
│           └────────────────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 🛠️ Technology Stack

| Component | Technology |
|-----------|------------|
| LLM | Anthropic Claude 4.5 via AWS Bedrock |
| Agent Framework | LangGraph |
| Protocol | Google A2A with SSE streaming |
| State Management | Redis Pub/Sub + Streams |
| Web Framework | FastAPI |
| Deployment | Kubernetes / Docker Compose |
| Language | Python 3.11+ |

## 📁 Project Structure

```
a2a_streaming/
├── common/                    # Shared A2A protocol implementation
│   ├── a2a_protocol.py       # A2A types and models
│   ├── a2a_server.py         # A2A server base class
│   ├── a2a_client.py         # A2A client for agent-to-agent calls
│   └── redis_manager.py      # Redis subscription/status manager
├── agents/
│   ├── intent_agent/         # Entry point - intent detection & routing
│   ├── booking_agent/        # Booking operations LangGraph agent
│   └── billing_agent/        # Billing operations LangGraph agent
├── demo/                     # Demo clients (CLI + Web)
├── k8s/                      # Kubernetes deployment manifests
├── docker/                   # Dockerfiles for each service
├── .github/                  # GitHub Actions CI/CD workflows
└── tests/                    # Test suite
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- AWS credentials configured for Bedrock access
- Redis (local or cluster)

### Local Development

```bash
# Clone the repository
git clone https://github.com/bssahu/a2a_streaming.git
cd a2a_streaming

# Install dependencies
make install

# Start Redis
make redis-start

# Start all agents (uses mock detector by default)
make dev

# In another terminal, run the demo
make demo-cli     # Terminal-based demo
make demo-web     # Web UI at http://localhost:8080
```

### Docker Compose

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Kubernetes Deployment

```bash
# Apply all manifests
make k8s-apply

# Check status
kubectl get pods -n a2a-customer-service

# Remove deployment
make k8s-delete
```

## 🔄 A2A Protocol Flow

### sendSubscribe Streaming

```
Client                    Intent Agent              Booking Agent
  │                            │                          │
  │──POST /tasks/sendSubscribe─▶│                          │
  │                            │                          │
  │◀────SSE: status=submitted──│                          │
  │◀────SSE: status=working────│ (Claude analyzes intent) │
  │◀────SSE: artifact──────────│ (intent detection result)│
  │                            │                          │
  │◀────SSE: status=working────│──POST sendSubscribe────▶│
  │                            │                          │
  │◀────SSE: status=working────│◀───SSE: working─────────│
  │◀────SSE: artifact──────────│◀───SSE: result──────────│
  │                            │                          │
  │◀────SSE: status=completed──│◀───SSE: completed───────│
```

### Agent Card Discovery

Each agent exposes its capabilities at `/.well-known/agent.json`:

```bash
curl http://localhost:8001/.well-known/agent.json
```

```json
{
  "name": "Intent Agent",
  "description": "Customer service entry point with intelligent intent detection",
  "capabilities": {
    "streaming": true
  },
  "skills": [
    {
      "id": "intent-detection",
      "name": "Intent Detection",
      "description": "Analyzes customer messages to determine intent"
    }
  ]
}
```

## ⚙️ Configuration

Copy `env.template` to `.env` and configure:

```bash
# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Redis
REDIS_URL=redis://localhost:6379

# Agent URLs
INTENT_AGENT_URL=http://localhost:8001
BOOKING_AGENT_URL=http://localhost:8002
BILLING_AGENT_URL=http://localhost:8003

# Development
USE_MOCK_DETECTOR=true  # Set to false to use real Claude
```

## 🧪 Testing

```bash
# Run all tests
make test

# Run with coverage
pytest tests/ -v --cov=common --cov=agents

# Run specific test file
pytest tests/common/test_redis_manager.py -v
```

## 📖 API Reference

### Send Task with Streaming

```bash
curl -N -X POST http://localhost:8001/tasks/sendSubscribe \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tasks/sendSubscribe",
    "params": {
      "id": "task-123",
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "Book an appointment for tomorrow"}]
      }
    }
  }'
```

### Resubscribe to Task

```bash
curl -N -X POST http://localhost:8001/tasks/resubscribe \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tasks/resubscribe",
    "params": {"id": "task-123"}
  }'
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Google A2A Protocol](https://github.com/google/A2A) - Agent-to-Agent communication standard
- [LangGraph](https://github.com/langchain-ai/langgraph) - State machine framework for agents
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework

## 📚 References

- [A2A Deep Dive: Getting Real-Time Updates from AI Agents](https://medium.com/google-cloud/a2a-deep-dive-getting-real-time-updates-from-ai-agents-a28d60317332)
- [A2A Protocol Specification](https://a2a.how/protocol)
