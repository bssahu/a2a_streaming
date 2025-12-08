"""
Intent Detection using Claude 4.5 via AWS Bedrock

Analyzes customer messages to determine intent and route to
the appropriate downstream agent.
"""

import json
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

import boto3
from botocore.config import Config
import structlog


logger = structlog.get_logger()


class Intent(str, Enum):
    """Supported customer service intents."""
    BOOKING = "booking"
    BILLING = "billing"
    GENERAL = "general"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of intent detection."""
    intent: Intent
    confidence: float
    reasoning: str
    extracted_entities: Dict[str, Any]
    suggested_response: Optional[str] = None


class IntentDetector:
    """
    Detects customer intent using Claude 4.5 via AWS Bedrock.
    
    Uses structured prompting to classify requests into:
    - booking: reservations, appointments, scheduling
    - billing: invoices, payments, refunds
    - general: general inquiries, feedback
    """
    
    # Claude 4.5 Sonnet model ID on Bedrock
    MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    
    SYSTEM_PROMPT = """You are an intent classification system for a customer service platform.

Your job is to analyze customer messages and determine:
1. The primary intent (booking, billing, or general)
2. Your confidence level (0.0 to 1.0)
3. Key entities mentioned (dates, amounts, names, etc.)
4. Brief reasoning for your classification

Intent Categories:
- booking: Any request related to reservations, appointments, scheduling, modifications, cancellations of bookings
- billing: Any request related to invoices, payments, refunds, charges, pricing, subscription billing
- general: General inquiries, feedback, complaints not specific to booking or billing

Always respond in the following JSON format:
{
    "intent": "booking" | "billing" | "general",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "entities": {
        "dates": [],
        "amounts": [],
        "names": [],
        "booking_ids": [],
        "invoice_ids": [],
        "other": {}
    }
}"""
    
    def __init__(
        self,
        region: str = "us-east-1",
        profile: Optional[str] = None,
    ):
        self.region = region
        
        # Configure boto3 client
        config = Config(
            region_name=region,
            retries={"max_attempts": 3, "mode": "adaptive"},
        )
        
        session_kwargs = {}
        if profile:
            session_kwargs["profile_name"] = profile
            
        session = boto3.Session(**session_kwargs)
        self.client = session.client(
            "bedrock-runtime",
            config=config,
        )
        
        logger.info("Initialized IntentDetector", region=region, model=self.MODEL_ID)
        
    async def detect(self, message: str) -> IntentResult:
        """
        Detect intent from a customer message.
        
        Args:
            message: The customer's message text
            
        Returns:
            IntentResult with detected intent and metadata
        """
        logger.info("Detecting intent", message_preview=message[:100])
        
        try:
            # Prepare the request for Claude
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": self.SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Classify this customer message:\n\n{message}",
                    }
                ],
            }
            
            # Call Bedrock
            response = self.client.invoke_model(
                modelId=self.MODEL_ID,
                body=json.dumps(request_body),
            )
            
            # Parse response
            response_body = json.loads(response["body"].read())
            content = response_body["content"][0]["text"]
            
            # Extract JSON from response
            result_data = self._parse_json_response(content)
            
            # Map to Intent enum
            intent_str = result_data.get("intent", "unknown").lower()
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.UNKNOWN
                
            result = IntentResult(
                intent=intent,
                confidence=float(result_data.get("confidence", 0.5)),
                reasoning=result_data.get("reasoning", ""),
                extracted_entities=result_data.get("entities", {}),
            )
            
            logger.info(
                "Intent detected",
                intent=result.intent,
                confidence=result.confidence,
                reasoning=result.reasoning,
            )
            
            return result
            
        except Exception as e:
            logger.error("Intent detection failed", error=str(e))
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                extracted_entities={},
            )
            
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Extract JSON from Claude's response."""
        # Try to parse the entire response as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
            
        # Try to find JSON in the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
                
        # Return a default structure
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reasoning": content,
            "entities": {},
        }


class IntentDetectorMock:
    """
    Mock intent detector for testing without Bedrock access.
    Uses keyword matching for basic intent detection.
    """
    
    BOOKING_KEYWORDS = [
        "book", "reserve", "appointment", "schedule", "reservation",
        "cancel booking", "modify booking", "change date", "reschedule",
    ]
    
    BILLING_KEYWORDS = [
        "invoice", "bill", "payment", "charge", "refund", "price",
        "subscription", "receipt", "statement", "pay", "cost",
    ]
    
    async def detect(self, message: str) -> IntentResult:
        """Detect intent using keyword matching."""
        message_lower = message.lower()
        
        booking_score = sum(1 for kw in self.BOOKING_KEYWORDS if kw in message_lower)
        billing_score = sum(1 for kw in self.BILLING_KEYWORDS if kw in message_lower)
        
        if booking_score > billing_score:
            intent = Intent.BOOKING
            confidence = min(0.9, 0.5 + booking_score * 0.1)
        elif billing_score > booking_score:
            intent = Intent.BILLING
            confidence = min(0.9, 0.5 + billing_score * 0.1)
        else:
            intent = Intent.GENERAL
            confidence = 0.5
            
        return IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=f"Keyword match: booking={booking_score}, billing={billing_score}",
            extracted_entities={},
        )

