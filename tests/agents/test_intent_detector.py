"""
Tests for Intent Detector.
"""

import pytest
from agents.intent_agent.intent_detector import (
    Intent,
    IntentResult,
    IntentDetectorMock,
)


@pytest.mark.asyncio
class TestIntentDetectorMock:
    """Tests for mock intent detector."""
    
    @pytest.fixture
    def detector(self):
        """Create a mock detector instance."""
        return IntentDetectorMock()
    
    async def test_detect_booking_intent(self, detector):
        """Test detecting booking intent."""
        messages = [
            "I want to book an appointment",
            "Can you reserve a table for Friday?",
            "I need to schedule a meeting",
            "Please cancel my reservation",
        ]
        
        for msg in messages:
            result = await detector.detect(msg)
            assert result.intent == Intent.BOOKING, f"Failed for: {msg}"
    
    async def test_detect_billing_intent(self, detector):
        """Test detecting billing intent."""
        messages = [
            "Show me my invoice",
            "I want to pay my bill",
            "Can I get a refund?",
            "What's my account balance?",
        ]
        
        for msg in messages:
            result = await detector.detect(msg)
            assert result.intent == Intent.BILLING, f"Failed for: {msg}"
    
    async def test_detect_general_intent(self, detector):
        """Test detecting general intent."""
        messages = [
            "Hello, how are you?",
            "What's the weather like?",
            "Tell me about your company",
        ]
        
        for msg in messages:
            result = await detector.detect(msg)
            assert result.intent == Intent.GENERAL, f"Failed for: {msg}"
    
    async def test_returns_intent_result(self, detector):
        """Test that detector returns IntentResult."""
        result = await detector.detect("Book a room")
        
        assert isinstance(result, IntentResult)
        assert isinstance(result.intent, Intent)
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1
        assert isinstance(result.reasoning, str)
        assert isinstance(result.extracted_entities, dict)
    
    async def test_confidence_increases_with_keywords(self, detector):
        """Test that confidence increases with more keywords."""
        result1 = await detector.detect("book")
        result2 = await detector.detect("book an appointment reservation")
        
        assert result2.confidence >= result1.confidence


class TestIntent:
    """Tests for Intent enum."""
    
    def test_intent_values(self):
        """Test intent enum values."""
        assert Intent.BOOKING.value == "booking"
        assert Intent.BILLING.value == "billing"
        assert Intent.GENERAL.value == "general"
        assert Intent.UNKNOWN.value == "unknown"


class TestIntentResult:
    """Tests for IntentResult dataclass."""
    
    def test_create_intent_result(self):
        """Test creating an IntentResult."""
        result = IntentResult(
            intent=Intent.BOOKING,
            confidence=0.95,
            reasoning="Multiple booking keywords detected",
            extracted_entities={"date": "tomorrow"},
        )
        
        assert result.intent == Intent.BOOKING
        assert result.confidence == 0.95
        assert result.reasoning == "Multiple booking keywords detected"
        assert result.extracted_entities["date"] == "tomorrow"
    
    def test_intent_result_with_suggestion(self):
        """Test IntentResult with suggested response."""
        result = IntentResult(
            intent=Intent.GENERAL,
            confidence=0.5,
            reasoning="No specific intent detected",
            extracted_entities={},
            suggested_response="How can I help you today?",
        )
        
        assert result.suggested_response == "How can I help you today?"

