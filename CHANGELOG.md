# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of A2A Customer Service Platform
- Intent Agent with Claude 4.5 (Bedrock) for intent detection
- Booking Agent with LangGraph workflow
- Billing Agent with LangGraph workflow
- Redis-backed state management and Pub/Sub streaming
- A2A protocol implementation with sendSubscribe support
- CLI and Web demo clients
- Docker Compose configuration
- Kubernetes deployment manifests
- GitHub Actions CI/CD workflows

## [1.0.0] - 2024-12-08

### Added
- **A2A Protocol Implementation**
  - Full `tasks/sendSubscribe` with SSE streaming
  - `tasks/resubscribe` for reconnection support
  - `tasks/send`, `tasks/get`, `tasks/cancel` endpoints
  - Agent Card discovery at `/.well-known/agent.json`

- **Intent Agent**
  - Claude 4.5 via AWS Bedrock for intent classification
  - Routing to booking/billing agents based on intent
  - Mock detector for development without AWS credentials

- **Booking Agent**
  - LangGraph state machine for booking workflow
  - Create, modify, cancel booking operations
  - Availability checking
  - Mock database for demonstration

- **Billing Agent**
  - LangGraph state machine for billing workflow
  - Invoice viewing and payment processing
  - Refund request handling
  - Account balance queries
  - Mock database for demonstration

- **Redis Manager**
  - Task state persistence with TTL
  - Pub/Sub for real-time status broadcasting
  - Redis Streams for event history (resubscription)
  - Subscription tracking across distributed pods

- **Demo Clients**
  - CLI client with colored terminal output
  - Web client with real-time flow visualization

- **Infrastructure**
  - Docker Compose for local development
  - Kubernetes manifests with HPA
  - GitHub Actions for CI/CD

### Technical Details
- Python 3.11+ required
- FastAPI for HTTP/SSE serving
- Pydantic v2 for data validation
- Async/await throughout for high concurrency

[Unreleased]: https://github.com/bssahu/a2a_streaming/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/bssahu/a2a_streaming/releases/tag/v1.0.0



