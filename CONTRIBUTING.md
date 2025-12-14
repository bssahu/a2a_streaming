# Contributing to A2A Customer Service

Thank you for your interest in contributing to this project! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to maintain a welcoming environment for everyone.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker (for running Redis and building images)
- AWS account with Bedrock access (for production use)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/bssahu/a2a_streaming.git
   cd a2a_streaming
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Redis**
   ```bash
   make redis-start
   ```

5. **Run the agents**
   ```bash
   make dev
   ```

## Development Workflow

### Branch Naming

- `feature/` - New features
- `bugfix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring

Example: `feature/add-cancellation-agent`

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(booking): add support for recurring appointments
fix(redis): handle connection timeout gracefully
docs(readme): update quick start instructions
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints for all function parameters and return values
- Add docstrings to all public functions and classes
- Keep functions focused and under 50 lines when possible

### Running Checks

Before submitting a PR, run:

```bash
# Linting
ruff check common/ agents/ demo/

# Type checking
mypy common/ agents/ --ignore-missing-imports

# Tests
pytest tests/ -v
```

## Project Structure

```
a2a_streaming/
├── common/           # Shared A2A protocol implementation
│   ├── a2a_protocol.py   # Protocol types and models
│   ├── a2a_server.py     # Base server class
│   ├── a2a_client.py     # Client implementation
│   └── redis_manager.py  # Redis state management
├── agents/
│   ├── intent_agent/     # Entry point agent
│   ├── booking_agent/    # Booking operations
│   └── billing_agent/    # Billing operations
├── demo/             # Demo clients
├── k8s/              # Kubernetes manifests
└── docker/           # Dockerfiles
```

## Adding a New Agent

1. Create a new directory under `agents/`:
   ```
   agents/
   └── new_agent/
       ├── __init__.py
       ├── agent.py      # A2AServer subclass
       ├── graph.py      # LangGraph workflow
       └── main.py       # Entry point
   ```

2. Implement the agent by extending `A2AServer`:
   ```python
   from common.a2a_server import A2AServer
   
   class NewAgent(A2AServer):
       async def process_task(self, task_id, message, session_id, metadata):
           # Your implementation
           yield TaskStatusUpdateEvent(...)
   ```

3. Add Dockerfile in `docker/Dockerfile.new_agent`

4. Add Kubernetes manifests in `k8s/new-agent.yaml`

5. Register the agent in the Intent Agent's routing logic

## Testing

### Unit Tests

Place tests in the `tests/` directory mirroring the source structure:

```
tests/
├── common/
│   └── test_redis_manager.py
├── agents/
│   └── intent_agent/
│       └── test_intent_detector.py
└── conftest.py
```

### Integration Tests

For integration tests that require Redis:

```python
import pytest

@pytest.fixture
async def redis_manager():
    manager = RedisManager(url="redis://localhost:6379")
    await manager.connect()
    yield manager
    await manager.disconnect()

async def test_task_storage(redis_manager):
    # Test implementation
```

## Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run all checks locally
5. Push to your fork
6. Open a Pull Request against `main`

### PR Requirements

- Clear description of changes
- All CI checks passing
- At least one approval from maintainers
- No merge conflicts

## Questions?

Open an issue with the `question` label or start a discussion in the Discussions tab.

Thank you for contributing! 🎉



