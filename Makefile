.PHONY: help install dev redis-start redis-stop test lint clean docker-build docker-up docker-down k8s-apply k8s-delete demo-cli demo-web

# Default target
help:
	@echo "A2A Customer Service - Available Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install      - Install Python dependencies"
	@echo "  make dev          - Start all agents locally (requires Redis)"
	@echo "  make demo-cli     - Run CLI demo client"
	@echo "  make demo-web     - Run web demo client"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make redis-start  - Start Redis container"
	@echo "  make redis-stop   - Stop Redis container"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker images"
	@echo "  make docker-up    - Start with Docker Compose"
	@echo "  make docker-down  - Stop Docker Compose"
	@echo ""
	@echo "Kubernetes:"
	@echo "  make k8s-apply    - Deploy to Kubernetes"
	@echo "  make k8s-delete   - Remove from Kubernetes"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linters"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        - Clean temporary files"

# Development
install:
	pip install -r requirements.txt

dev:
	@chmod +x scripts/run_local.sh
	@./scripts/run_local.sh

demo-cli:
	python -m demo.client

demo-web:
	python -m demo.web_client

# Redis
redis-start:
	docker run -d --name a2a-redis -p 6379:6379 redis:7-alpine

redis-stop:
	docker stop a2a-redis && docker rm a2a-redis

# Testing
test:
	pytest tests/ -v

lint:
	mypy common/ agents/ --ignore-missing-imports
	ruff check common/ agents/

# Docker
docker-build:
	docker build -f docker/Dockerfile.intent -t a2a-streaming/intent-agent:latest .
	docker build -f docker/Dockerfile.booking -t a2a-streaming/booking-agent:latest .
	docker build -f docker/Dockerfile.billing -t a2a-streaming/billing-agent:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# Kubernetes
k8s-apply:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/secrets.yaml
	kubectl apply -f k8s/redis.yaml
	kubectl apply -f k8s/intent-agent.yaml
	kubectl apply -f k8s/booking-agent.yaml
	kubectl apply -f k8s/billing-agent.yaml
	kubectl apply -f k8s/hpa.yaml

k8s-delete:
	kubectl delete -f k8s/ --ignore-not-found

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf .ruff_cache



