"""
Configuration settings for the AI service
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Google Gemini
    GOOGLE_API_KEY: Optional[str] = None

    # Shopify Store (for direct testing)
    SHOPIFY_STORE_DOMAIN: Optional[str] = None
    SHOPIFY_ACCESS_TOKEN: Optional[str] = None

    # Redis (optional)
    REDIS_URL: Optional[str] = "redis://localhost:6379"

    # Cache settings
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Shopify API version
    SHOPIFY_API_VERSION: str = "2024-01"

    # Agent settings
    MAX_RETRIES: int = 3
    LLM_TEMPERATURE: float = 0.3
    LLM_MODEL: str = "gemini-1.5-flash"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
