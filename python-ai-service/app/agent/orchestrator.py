"""
Agent Orchestrator - Main workflow coordinator for the AI analytics agent

This module implements the agentic workflow:
1. Intent Classification - Understand what the user is asking
2. Query Planning - Determine what data is needed
3. ShopifyQL Generation - Build the appropriate query
4. Query Validation - Ensure query correctness
5. Execution - Run the query against Shopify
6. Response Formatting - Convert to business-friendly language
"""
import uuid
from typing import Optional, Dict, Any
import structlog

from app.agent.intent_classifier import IntentClassifier
from app.agent.query_generator import QueryGenerator
from app.agent.query_validator import QueryValidator
from app.agent.response_formatter import ResponseFormatter
from app.shopify.client import ShopifyClient
from app.cache.redis_cache import CacheManager
from app.memory.conversation_store import ConversationStore

logger = structlog.get_logger()


class AgentOrchestrator:
    """
    Main orchestrator for the AI analytics agent.
    Coordinates all components to process user questions.
    """

    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.query_generator = QueryGenerator()
        self.query_validator = QueryValidator()
        self.response_formatter = ResponseFormatter()
        self.cache_manager = CacheManager()
        self.conversation_store = ConversationStore()

    async def process_question(
        self,
        store_id: str,
        question: str,
        access_token: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a natural language question and return an answer.

        Args:
            store_id: Shopify store domain
            question: User's natural language question
            access_token: Shopify API access token
            conversation_id: Optional ID for conversation continuity

        Returns:
            Dictionary with answer, confidence, query used, and conversation ID
        """
        # Generate or use existing conversation ID
        conv_id = conversation_id or str(uuid.uuid4())

        # Get conversation history for context
        history = self.conversation_store.get_history(conv_id)

        logger.info(
            "processing_question",
            store_id=store_id,
            question=question[:100],
            has_history=len(history) > 0
        )

        try:
            # Step 1: Classify intent
            intent_result = await self.intent_classifier.classify(
                question=question,
                conversation_history=history
            )

            logger.info(
                "intent_classified",
                intent=intent_result["intent"],
                entities=intent_result.get("entities", {})
            )

            # Step 2: Generate ShopifyQL query
            query_result = await self.query_generator.generate(
                question=question,
                intent=intent_result["intent"],
                entities=intent_result.get("entities", {}),
                conversation_history=history
            )

            shopifyql_query = query_result["query"]

            logger.info(
                "query_generated",
                query=shopifyql_query[:200] if shopifyql_query else None
            )

            # Step 3: Validate the query
            is_valid, validation_errors = self.query_validator.validate(shopifyql_query)

            if not is_valid:
                logger.warning(
                    "query_validation_failed",
                    errors=validation_errors
                )
                # Try to regenerate with error feedback
                query_result = await self.query_generator.regenerate_with_errors(
                    original_query=shopifyql_query,
                    errors=validation_errors,
                    question=question,
                    intent=intent_result["intent"]
                )
                shopifyql_query = query_result["query"]

                # Validate again
                is_valid, validation_errors = self.query_validator.validate(shopifyql_query)
                if not is_valid:
                    return self._error_response(
                        conv_id,
                        "Unable to generate a valid query for your question. Please try rephrasing.",
                        validation_errors
                    )

            # Step 4: Check cache
            cache_key = self.cache_manager.generate_key(store_id, shopifyql_query)
            cached_result = await self.cache_manager.get(cache_key)

            if cached_result:
                logger.info("cache_hit", cache_key=cache_key)
                query_data = cached_result
            else:
                # Step 5: Execute query against Shopify with fallback chain
                # ShopifyQL is tried first, with GraphQL as fallback for dev stores
                shopify_client = ShopifyClient(store_id, access_token)
                query_data = await shopify_client.execute_query_with_fallback(
                    shopifyql_query=shopifyql_query,
                    intent=intent_result["intent"],
                    entities=intent_result.get("entities", {})
                )

                # Log which method was used
                if query_data.get("fallback_used"):
                    logger.info(
                        "query_executed_with_fallback",
                        source=query_data.get("source"),
                        shopifyql_error=query_data.get("shopifyql_error")
                    )

                # Cache the result
                await self.cache_manager.set(cache_key, query_data)

            logger.info(
                "query_executed",
                row_count=len(query_data.get("data", []))
            )

            # Step 6: Format response in business-friendly language
            formatted_response = await self.response_formatter.format(
                question=question,
                intent=intent_result["intent"],
                query_data=query_data,
                entities=intent_result.get("entities", {})
            )

            # Store in conversation history
            self.conversation_store.add_turn(
                conversation_id=conv_id,
                question=question,
                answer=formatted_response["answer"],
                query=shopifyql_query,
                intent=intent_result["intent"]
            )

            # Determine which query method was actually used
            data_source = query_data.get("source", "shopifyql")
            fallback_used = query_data.get("fallback_used", False)

            return {
                "answer": formatted_response["answer"],
                "confidence": formatted_response.get("confidence", "medium"),
                "query_used": shopifyql_query,
                "data_source": data_source,
                "fallback_used": fallback_used,
                "raw_data": query_data if query_data else None,
                "conversation_id": conv_id,
                "error": None
            }

        except Exception as e:
            logger.error(
                "orchestration_error",
                error=str(e),
                store_id=store_id
            )
            return self._error_response(conv_id, str(e))

    def _error_response(
        self,
        conversation_id: str,
        error_message: str,
        details: list = None
    ) -> Dict[str, Any]:
        """Generate an error response"""
        return {
            "answer": f"I encountered an issue processing your question: {error_message}",
            "confidence": "low",
            "query_used": None,
            "raw_data": None,
            "conversation_id": conversation_id,
            "error": error_message
        }
