#!/bin/bash

# Quick test script for A2A sendSubscribe
# Usage: ./scripts/test_request.sh "Your message here"

MESSAGE=${1:-"I would like to book an appointment for tomorrow at 2pm"}

echo "Sending request to Intent Agent..."
echo "Message: $MESSAGE"
echo ""
echo "Response (SSE stream):"
echo "======================"

curl -N -X POST http://localhost:8001/tasks/sendSubscribe \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": \"test-$(date +%s)\",
    \"method\": \"tasks/sendSubscribe\",
    \"params\": {
      \"id\": \"task-$(date +%s)\",
      \"message\": {
        \"role\": \"user\",
        \"parts\": [{\"type\": \"text\", \"text\": \"$MESSAGE\"}]
      }
    }
  }"

echo ""



