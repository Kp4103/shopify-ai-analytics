"""
Intent Classifier - Understands user questions and extracts relevant entities

Classifies questions into categories:
- inventory: Stock levels, reorder suggestions, out-of-stock predictions
- sales: Revenue, top products, trends, order counts
- customers: Repeat customers, customer value, segments
- orders: Order status, fulfillment, returns
"""
import json
from typing import Dict, Any, List, Optional
import structlog

from app.llm.gemini_client import GeminiClient

logger = structlog.get_logger()

INTENT_CLASSIFICATION_PROMPT = """You are an expert at understanding e-commerce analytics questions.

Analyze the following question and classify it into one of these categories:
- inventory: Questions about stock levels, inventory counts, product listings, product catalog, what products exist, reorder suggestions, out-of-stock predictions. Use this for "list my products", "show products", "what products do I have"
- sales: Questions about revenue, top-selling products by SALES/REVENUE, sales trends, order amounts, money earned
- customers: Questions about customer behavior, repeat customers, customer segments, customer value
- orders: Questions about order status, fulfillment, shipping, returns

IMPORTANT: If someone asks to "list products" or "show products" or "what products do I have", classify as "inventory" (not sales).

Also extract relevant entities from the question:
- time_period: The time range mentioned (e.g., "last week", "last 30 days", "this month")
- product_name: Specific product mentioned (if any)
- metric: What metric is being asked about (e.g., "units sold", "revenue", "stock level")
- limit: Any numeric limit mentioned (e.g., "top 5", "first 10")

Question: {question}

{conversation_context}

Respond in JSON format:
{{
    "intent": "inventory|sales|customers|orders",
    "confidence": "high|medium|low",
    "entities": {{
        "time_period": "string or null",
        "product_name": "string or null",
        "metric": "string or null",
        "limit": "number or null"
    }},
    "reasoning": "Brief explanation of why this classification was chosen"
}}
"""


class IntentClassifier:
    """Classifies user questions and extracts relevant entities"""

    def __init__(self):
        self.llm = GeminiClient()

    async def classify(
        self,
        question: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Classify the intent of a user question.

        Args:
            question: The user's natural language question
            conversation_history: Previous conversation turns for context

        Returns:
            Dictionary with intent, confidence, and extracted entities
        """
        # Build conversation context if available
        context = ""
        if conversation_history:
            context = "Previous conversation:\n"
            for turn in conversation_history[-3:]:  # Last 3 turns for context
                context += f"User: {turn.get('question', '')}\n"
                context += f"Assistant: {turn.get('answer', '')[:200]}...\n"
            context = f"\nConversation context:\n{context}"

        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            question=question,
            conversation_context=context
        )

        try:
            response = await self.llm.generate(prompt)

            # Parse JSON response
            result = self._parse_response(response)

            logger.info(
                "intent_classified",
                intent=result["intent"],
                confidence=result.get("confidence", "medium")
            )

            return result

        except Exception as e:
            logger.error("intent_classification_error", error=str(e))
            # Return a default classification on error
            return self._default_classification(question)

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM response into structured data"""
        try:
            # Try to extract JSON from the response
            # Handle cases where LLM might include markdown code blocks
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response.strip())

            # Validate required fields
            if "intent" not in result:
                result["intent"] = "sales"  # Default
            if "entities" not in result:
                result["entities"] = {}

            # Ensure intent is valid
            valid_intents = ["inventory", "sales", "customers", "orders"]
            if result["intent"] not in valid_intents:
                result["intent"] = "sales"

            return result

        except json.JSONDecodeError as e:
            logger.warning("json_parse_error", error=str(e), response=response[:200])
            return self._default_classification("")

    def _default_classification(self, question: str) -> Dict[str, Any]:
        """Return a default classification based on keyword matching"""
        question_lower = question.lower()

        # Simple keyword-based fallback
        if any(word in question_lower for word in ["stock", "inventory", "reorder", "out of stock", "product", "products", "catalog", "list"]):
            intent = "inventory"
        elif any(word in question_lower for word in ["customer", "repeat", "buyer", "purchased"]):
            intent = "customers"
        elif any(word in question_lower for word in ["order", "fulfillment", "shipping", "return"]):
            intent = "orders"
        else:
            intent = "sales"

        return {
            "intent": intent,
            "confidence": "low",
            "entities": {
                "time_period": None,
                "product_name": None,
                "metric": None,
                "limit": None
            },
            "reasoning": "Fallback classification based on keywords"
        }
