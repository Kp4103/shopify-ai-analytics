"""
FastAPI AI Service for Shopify Analytics
Main entry point for the application
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import structlog

from app.agent.orchestrator import AgentOrchestrator
from app.config import settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

app = FastAPI(
    title="Shopify AI Analytics Service",
    description="LLM-powered analytics agent for Shopify stores",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the agent orchestrator
orchestrator = AgentOrchestrator()


class QuestionRequest(BaseModel):
    """Request model for analytics questions"""
    store_id: str = Field(..., description="Shopify store domain (e.g., example-store.myshopify.com)")
    question: str = Field(..., description="Natural language question about store analytics")
    access_token: str = Field(..., description="Shopify API access token")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID for follow-up questions")


class QuestionResponse(BaseModel):
    """Response model for analytics answers"""
    answer: str = Field(..., description="Human-readable answer to the question")
    confidence: str = Field(..., description="Confidence level: high, medium, or low")
    query_used: Optional[str] = Field(None, description="ShopifyQL query that was executed")
    raw_data: Optional[dict] = Field(None, description="Raw data from query (if requested)")
    conversation_id: str = Field(..., description="Conversation ID for follow-up questions")
    error: Optional[str] = Field(None, description="Error message if something went wrong")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "service": "shopify-ai-analytics"}


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "gemini_configured": bool(settings.GOOGLE_API_KEY),
        "redis_configured": bool(settings.REDIS_URL)
    }


@app.post("/api/v1/analyze", response_model=QuestionResponse)
async def analyze_question(request: QuestionRequest):
    """
    Process a natural language question about Shopify store analytics.

    The agent will:
    1. Classify the intent (inventory, sales, customers, orders)
    2. Generate appropriate ShopifyQL query
    3. Execute the query against Shopify API
    4. Convert results to business-friendly language
    """
    logger.info(
        "received_question",
        store_id=request.store_id,
        question=request.question[:100],
        conversation_id=request.conversation_id
    )

    try:
        result = await orchestrator.process_question(
            store_id=request.store_id,
            question=request.question,
            access_token=request.access_token,
            conversation_id=request.conversation_id
        )

        logger.info(
            "question_processed",
            store_id=request.store_id,
            confidence=result.get("confidence"),
            conversation_id=result.get("conversation_id")
        )

        return QuestionResponse(**result)

    except Exception as e:
        logger.error(
            "question_processing_error",
            store_id=request.store_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/validate-query")
async def validate_query(query: str):
    """
    Validate a ShopifyQL query without executing it.
    Useful for testing query generation.
    """
    from app.agent.query_validator import QueryValidator

    validator = QueryValidator()
    is_valid, errors = validator.validate(query)

    return {
        "valid": is_valid,
        "errors": errors,
        "query": query
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
