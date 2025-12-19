"""
Gemini Client - Wrapper for Google's Gemini API

Handles all LLM interactions with error handling, retries, and logging.
"""
import asyncio
from typing import Optional
import structlog
import google.generativeai as genai

from app.config import settings

logger = structlog.get_logger()


class GeminiClient:
    """Client for interacting with Google's Gemini API"""

    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.model_name = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_retries = settings.MAX_RETRIES

        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None
            logger.warning("gemini_not_configured", message="GOOGLE_API_KEY not set, using mock responses")

    async def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 2048
    ) -> str:
        """
        Generate a response from the Gemini model.

        Args:
            prompt: The prompt to send to the model
            temperature: Optional temperature override
            max_tokens: Maximum tokens in response

        Returns:
            The generated text response
        """
        if not self.model:
            return self._mock_response(prompt)

        temp = temperature if temperature is not None else self.temperature

        generation_config = genai.types.GenerationConfig(
            temperature=temp,
            max_output_tokens=max_tokens,
        )

        for attempt in range(self.max_retries):
            try:
                # Run the synchronous API call in a thread pool
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.model.generate_content(
                        prompt,
                        generation_config=generation_config
                    )
                )

                if response.text:
                    logger.info(
                        "gemini_response_generated",
                        prompt_length=len(prompt),
                        response_length=len(response.text)
                    )
                    return response.text
                else:
                    logger.warning("gemini_empty_response", attempt=attempt)

            except Exception as e:
                logger.error(
                    "gemini_generation_error",
                    error=str(e),
                    attempt=attempt + 1,
                    max_retries=self.max_retries
                )

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

        return self._mock_response(prompt)

    def _mock_response(self, prompt: str) -> str:
        """Generate a mock response for testing without API key"""
        logger.info("generating_mock_response")

        # Detect what kind of response is needed based on prompt content
        prompt_lower = prompt.lower()

        if "intent" in prompt_lower or "classify" in prompt_lower:
            return '''{
    "intent": "sales",
    "confidence": "high",
    "entities": {
        "time_period": "last 7 days",
        "product_name": null,
        "metric": "sales",
        "limit": 5
    },
    "reasoning": "Mock classification - question appears to be about sales data"
}'''

        elif "shopifyql" in prompt_lower or "query" in prompt_lower:
            return '''{
    "query": "FROM sales SHOW product_title, sum(net_sales) AS total_sales, sum(net_quantity) AS units_sold SINCE -7d UNTIL today GROUP BY product_title ORDER BY total_sales DESC LIMIT 5",
    "explanation": "This query retrieves the top 5 selling products by revenue over the last 7 days",
    "fields_used": ["product_title", "net_sales", "net_quantity"],
    "table": "sales"
}'''

        elif "format" in prompt_lower or "response" in prompt_lower:
            return '''{
    "answer": "Based on your store's data from the last 7 days, here are your top 5 selling products: 1) Blue T-Shirt ($1,234.56, 45 units), 2) Black Jeans ($987.65, 32 units), 3) White Sneakers ($876.54, 28 units), 4) Red Cap ($543.21, 25 units), 5) Green Hoodie ($432.10, 20 units). Your Blue T-Shirt continues to be the best performer!",
    "confidence": "high",
    "key_insights": ["Blue T-Shirt is your top seller", "Total of 150 units sold across top 5 products"],
    "recommendations": ["Consider restocking Blue T-Shirts", "Review pricing strategy for lower performers"]
}'''

        else:
            return "Mock response - Please configure GOOGLE_API_KEY for real responses"
