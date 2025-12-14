"""
Intent Agent - Entry Point

Handles incoming customer requests, detects intent using Claude 4.5,
and routes to appropriate downstream agents with status streaming.
"""

from .agent import IntentAgent
from .intent_detector import IntentDetector, Intent

__all__ = ["IntentAgent", "IntentDetector", "Intent"]



