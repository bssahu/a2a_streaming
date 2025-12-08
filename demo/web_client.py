"""
Web-based Demo Client for A2A Customer Service

Provides a beautiful web UI for demonstrating the A2A streaming
flow with real-time visualization.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.a2a_client import A2AClient
from common.a2a_protocol import (
    Message,
    TextPart,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)


load_dotenv()

app = FastAPI(title="A2A Customer Service Demo")

# Intent Agent URL
INTENT_AGENT_URL = os.getenv("INTENT_AGENT_URL", "http://localhost:8001")


# HTML template with embedded CSS and JS
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2A Customer Service - Status Streaming Demo</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e14;
            --bg-secondary: #0d1117;
            --bg-card: #161b22;
            --bg-card-hover: #1c2128;
            --border-color: #30363d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            
            --accent-blue: #58a6ff;
            --accent-green: #3fb950;
            --accent-yellow: #d29922;
            --accent-red: #f85149;
            --accent-purple: #a371f7;
            --accent-cyan: #39d0d0;
            
            --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --gradient-success: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            --gradient-working: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        /* Background pattern */
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(ellipse at 20% 20%, rgba(88, 166, 255, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 80%, rgba(163, 113, 247, 0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 50%, rgba(57, 208, 208, 0.03) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px;
            position: relative;
            z-index: 1;
        }
        
        /* Header */
        .header {
            text-align: center;
            padding: 40px 0;
            margin-bottom: 32px;
        }
        
        .header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 12px;
        }
        
        .header p {
            color: var(--text-secondary);
            font-size: 1.1rem;
            max-width: 600px;
            margin: 0 auto;
        }
        
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 16px;
        }
        
        .badge .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* Main layout */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 24px;
        }
        
        @media (max-width: 1024px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }
        
        /* Cards */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
        }
        
        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .card-title {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .card-body {
            padding: 20px;
        }
        
        /* Input section */
        .input-section {
            margin-bottom: 24px;
        }
        
        .input-wrapper {
            position: relative;
        }
        
        .message-input {
            width: 100%;
            padding: 16px 120px 16px 20px;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            border-radius: 12px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 1rem;
            transition: all 0.2s;
        }
        
        .message-input:focus {
            outline: none;
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 4px rgba(88, 166, 255, 0.1);
        }
        
        .message-input::placeholder {
            color: var(--text-muted);
        }
        
        .send-btn {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            padding: 10px 20px;
            background: var(--gradient-primary);
            border: none;
            border-radius: 8px;
            color: white;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .send-btn:hover {
            transform: translateY(-50%) scale(1.02);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: translateY(-50%);
        }
        
        /* Suggestions */
        .suggestions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }
        
        .suggestion-chip {
            padding: 8px 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .suggestion-chip:hover {
            background: var(--bg-card-hover);
            border-color: var(--accent-blue);
            color: var(--text-primary);
        }
        
        /* Status stream */
        .stream-container {
            height: 500px;
            overflow-y: auto;
            padding-right: 8px;
        }
        
        .stream-container::-webkit-scrollbar {
            width: 6px;
        }
        
        .stream-container::-webkit-scrollbar-track {
            background: transparent;
        }
        
        .stream-container::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 3px;
        }
        
        .event-item {
            padding: 16px;
            margin-bottom: 12px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .event-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        
        .event-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
        }
        
        .event-icon.submitted { background: rgba(210, 153, 34, 0.2); }
        .event-icon.working { background: rgba(88, 166, 255, 0.2); }
        .event-icon.completed { background: rgba(63, 185, 80, 0.2); }
        .event-icon.failed { background: rgba(248, 81, 73, 0.2); }
        .event-icon.artifact { background: rgba(57, 208, 208, 0.2); }
        
        .event-state {
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .event-state.submitted { color: var(--accent-yellow); }
        .event-state.working { color: var(--accent-blue); }
        .event-state.completed { color: var(--accent-green); }
        .event-state.failed { color: var(--accent-red); }
        .event-state.artifact { color: var(--accent-cyan); }
        
        .event-timestamp {
            margin-left: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        .event-message {
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.5;
        }
        
        .artifact-content {
            margin-top: 12px;
            padding: 12px;
            background: var(--bg-primary);
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--text-secondary);
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 200px;
            overflow-y: auto;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }
        
        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        
        /* Flow diagram */
        .flow-diagram {
            padding: 20px;
        }
        
        .flow-node {
            padding: 12px 16px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: all 0.3s;
        }
        
        .flow-node.active {
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 4px rgba(88, 166, 255, 0.1);
        }
        
        .flow-node.complete {
            border-color: var(--accent-green);
        }
        
        .flow-node-icon {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
        }
        
        .flow-node-icon.intent { background: rgba(163, 113, 247, 0.2); }
        .flow-node-icon.booking { background: rgba(63, 185, 80, 0.2); }
        .flow-node-icon.billing { background: rgba(88, 166, 255, 0.2); }
        
        .flow-node-label {
            font-weight: 500;
            font-size: 0.9rem;
        }
        
        .flow-node-status {
            margin-left: auto;
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        .flow-connector {
            width: 2px;
            height: 20px;
            background: var(--border-color);
            margin-left: 28px;
        }
        
        .flow-connector.active {
            background: var(--accent-blue);
        }
        
        /* Metrics */
        .metrics {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-top: 20px;
        }
        
        .metric-card {
            padding: 16px;
            background: var(--bg-secondary);
            border-radius: 10px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .metric-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>🤖 A2A Customer Service</h1>
            <p>Real-time status streaming demonstration using Google's Agent-to-Agent protocol</p>
            <div class="badge">
                <span class="dot"></span>
                <span>Powered by Claude 4.5 + LangGraph</span>
            </div>
        </header>
        
        <div class="main-grid">
            <div class="main-content">
                <div class="card input-section">
                    <div class="card-body">
                        <div class="input-wrapper">
                            <input 
                                type="text" 
                                id="messageInput" 
                                class="message-input" 
                                placeholder="Ask about bookings, billing, or general inquiries..."
                                autocomplete="off"
                            >
                            <button id="sendBtn" class="send-btn">Send →</button>
                        </div>
                        <div class="suggestions">
                            <span class="suggestion-chip" data-msg="Book an appointment for tomorrow at 2pm">📅 Book appointment</span>
                            <span class="suggestion-chip" data-msg="Show me my pending invoices">💳 View invoices</span>
                            <span class="suggestion-chip" data-msg="Check availability for next Monday">📆 Check availability</span>
                            <span class="suggestion-chip" data-msg="I need a refund for my last payment">💸 Request refund</span>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">
                            <span>📡</span> Status Stream
                        </span>
                        <button id="clearBtn" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem;">Clear</button>
                    </div>
                    <div class="card-body">
                        <div id="streamContainer" class="stream-container">
                            <div class="empty-state">
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                                </svg>
                                <p>Send a message to see real-time status updates</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <aside class="sidebar">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">
                            <span>🔄</span> Request Flow
                        </span>
                    </div>
                    <div class="flow-diagram">
                        <div id="flowIntent" class="flow-node">
                            <div class="flow-node-icon intent">🎯</div>
                            <div>
                                <div class="flow-node-label">Intent Agent</div>
                            </div>
                            <div class="flow-node-status" id="intentStatus">Idle</div>
                        </div>
                        <div id="flowConnector1" class="flow-connector"></div>
                        <div id="flowBooking" class="flow-node" style="opacity: 0.5;">
                            <div class="flow-node-icon booking">📅</div>
                            <div>
                                <div class="flow-node-label">Booking Agent</div>
                            </div>
                            <div class="flow-node-status" id="bookingStatus">—</div>
                        </div>
                        <div id="flowConnector2" class="flow-connector"></div>
                        <div id="flowBilling" class="flow-node" style="opacity: 0.5;">
                            <div class="flow-node-icon billing">💳</div>
                            <div>
                                <div class="flow-node-label">Billing Agent</div>
                            </div>
                            <div class="flow-node-status" id="billingStatus">—</div>
                        </div>
                    </div>
                    
                    <div class="metrics">
                        <div class="metric-card">
                            <div class="metric-value" id="eventCount">0</div>
                            <div class="metric-label">Events</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value" id="responseTime">—</div>
                            <div class="metric-label">Response Time</div>
                        </div>
                    </div>
                </div>
            </aside>
        </div>
    </div>
    
    <script>
        const streamContainer = document.getElementById('streamContainer');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const clearBtn = document.getElementById('clearBtn');
        const eventCountEl = document.getElementById('eventCount');
        const responseTimeEl = document.getElementById('responseTime');
        
        let ws = null;
        let eventCount = 0;
        let startTime = null;
        
        // WebSocket connection
        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleEvent(data);
            };
            
            ws.onclose = () => {
                setTimeout(connect, 1000);
            };
        }
        
        // Handle incoming events
        function handleEvent(data) {
            eventCount++;
            eventCountEl.textContent = eventCount;
            
            // Remove empty state
            const emptyState = streamContainer.querySelector('.empty-state');
            if (emptyState) emptyState.remove();
            
            // Create event element
            const eventEl = document.createElement('div');
            eventEl.className = 'event-item';
            
            const timestamp = new Date().toLocaleTimeString('en-US', { 
                hour12: false, 
                hour: '2-digit', 
                minute: '2-digit',
                second: '2-digit',
                fractionalSecondDigits: 3
            });
            
            if (data.type === 'status') {
                const state = data.status.state;
                const message = data.status.message?.parts?.[0]?.text || state;
                
                eventEl.innerHTML = `
                    <div class="event-header">
                        <div class="event-icon ${state}">${getStateIcon(state)}</div>
                        <span class="event-state ${state}">${state}</span>
                        <span class="event-timestamp">${timestamp}</span>
                    </div>
                    <div class="event-message">${message}</div>
                `;
                
                // Update flow diagram
                updateFlowDiagram(state, message);
                
                // Update response time on completion
                if (state === 'completed' || state === 'failed') {
                    if (startTime) {
                        const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
                        responseTimeEl.textContent = `${elapsed}s`;
                    }
                    sendBtn.disabled = false;
                }
            } else if (data.type === 'artifact') {
                const name = data.artifact.name || 'Result';
                const content = data.artifact.parts?.[0]?.text || '';
                
                eventEl.innerHTML = `
                    <div class="event-header">
                        <div class="event-icon artifact">📦</div>
                        <span class="event-state artifact">${name}</span>
                        <span class="event-timestamp">${timestamp}</span>
                    </div>
                    <div class="artifact-content">${formatArtifactContent(content)}</div>
                `;
            }
            
            streamContainer.appendChild(eventEl);
            streamContainer.scrollTop = streamContainer.scrollHeight;
        }
        
        function getStateIcon(state) {
            const icons = {
                'submitted': '📤',
                'working': '⚙️',
                'completed': '✅',
                'failed': '❌',
                'canceled': '🚫',
                'input-required': '❓'
            };
            return icons[state] || '•';
        }
        
        function formatArtifactContent(content) {
            try {
                const parsed = JSON.parse(content);
                return JSON.stringify(parsed, null, 2);
            } catch {
                return content;
            }
        }
        
        function updateFlowDiagram(state, message) {
            const intentNode = document.getElementById('flowIntent');
            const bookingNode = document.getElementById('flowBooking');
            const billingNode = document.getElementById('flowBilling');
            const connector1 = document.getElementById('flowConnector1');
            const connector2 = document.getElementById('flowConnector2');
            
            // Reset
            [intentNode, bookingNode, billingNode].forEach(n => {
                n.classList.remove('active', 'complete');
            });
            [connector1, connector2].forEach(c => c.classList.remove('active'));
            
            // Detect active agent from message
            const msgLower = message.toLowerCase();
            
            if (msgLower.includes('booking')) {
                intentNode.classList.add('complete');
                connector1.classList.add('active');
                bookingNode.classList.add('active');
                bookingNode.style.opacity = '1';
                document.getElementById('bookingStatus').textContent = state;
                document.getElementById('intentStatus').textContent = 'Done';
            } else if (msgLower.includes('billing')) {
                intentNode.classList.add('complete');
                connector2.classList.add('active');
                billingNode.classList.add('active');
                billingNode.style.opacity = '1';
                document.getElementById('billingStatus').textContent = state;
                document.getElementById('intentStatus').textContent = 'Done';
            } else {
                intentNode.classList.add('active');
                document.getElementById('intentStatus').textContent = state;
            }
            
            if (state === 'completed') {
                intentNode.classList.remove('active');
                intentNode.classList.add('complete');
                bookingNode.classList.remove('active');
                bookingNode.classList.add('complete');
                billingNode.classList.remove('active');
                billingNode.classList.add('complete');
            }
        }
        
        // Send message
        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message || !ws) return;
            
            sendBtn.disabled = true;
            startTime = Date.now();
            eventCount = 0;
            eventCountEl.textContent = '0';
            responseTimeEl.textContent = '—';
            
            // Reset flow
            document.getElementById('intentStatus').textContent = 'Processing...';
            document.getElementById('bookingStatus').textContent = '—';
            document.getElementById('billingStatus').textContent = '—';
            document.getElementById('flowBooking').style.opacity = '0.5';
            document.getElementById('flowBilling').style.opacity = '0.5';
            
            ws.send(JSON.stringify({ message }));
            messageInput.value = '';
            messageInput.focus();
        }
        
        // Event listeners
        sendBtn.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        
        clearBtn.addEventListener('click', () => {
            streamContainer.innerHTML = `
                <div class="empty-state">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                    </svg>
                    <p>Send a message to see real-time status updates</p>
                </div>
            `;
            eventCount = 0;
            eventCountEl.textContent = '0';
        });
        
        // Suggestion chips
        document.querySelectorAll('.suggestion-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                messageInput.value = chip.dataset.msg;
                messageInput.focus();
            });
        });
        
        // Initialize
        connect();
        messageInput.focus();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the demo UI."""
    return HTML_TEMPLATE


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for streaming A2A events to the browser."""
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_text = data.get("message", "")
            
            if not message_text:
                continue
            
            # Create A2A client and send request
            async with A2AClient(INTENT_AGENT_URL) as client:
                message = Message(
                    role="user",
                    parts=[TextPart(text=message_text)],
                )
                
                try:
                    async for event in client.send_subscribe(message):
                        if isinstance(event, TaskStatusUpdateEvent):
                            await websocket.send_json({
                                "type": "status",
                                "id": event.id,
                                "status": {
                                    "state": event.status.state.value,
                                    "message": {
                                        "parts": [
                                            {"text": p.text}
                                            for p in (event.status.message.parts if event.status.message else [])
                                            if hasattr(p, "text")
                                        ]
                                    } if event.status.message else None,
                                },
                                "final": event.final,
                            })
                        elif isinstance(event, TaskArtifactUpdateEvent):
                            await websocket.send_json({
                                "type": "artifact",
                                "id": event.id,
                                "artifact": {
                                    "name": event.artifact.name,
                                    "parts": [
                                        {"text": p.text}
                                        for p in event.artifact.parts
                                        if hasattr(p, "text")
                                    ],
                                },
                            })
                except Exception as e:
                    await websocket.send_json({
                        "type": "status",
                        "status": {
                            "state": "failed",
                            "message": {"parts": [{"text": f"Error: {str(e)}"}]},
                        },
                        "final": True,
                    })
                    
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="A2A Web Demo Client")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()
    
    print(f"\n🚀 Starting A2A Demo Web Client")
    print(f"   Open http://localhost:{args.port} in your browser")
    print(f"   Connecting to Intent Agent at {INTENT_AGENT_URL}\n")
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )

