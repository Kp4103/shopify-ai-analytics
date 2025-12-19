"""
Redis Cache Manager - Caches Shopify API responses

Provides a caching layer to reduce API calls and improve response times.
Falls back to in-memory caching if Redis is unavailable.
"""
import json
import hashlib
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import structlog

from app.config import settings

logger = structlog.get_logger()

# Try to import redis, fall back to in-memory if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis_not_available", message="Using in-memory cache")


class InMemoryCache:
    """Simple in-memory cache fallback"""

    def __init__(self):
        self._cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)

    async def get(self, key: str) -> Optional[str]:
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                return value
            else:
                del self._cache[key]
        return None

    async def set(self, key: str, value: str, ttl: int) -> bool:
        expiry = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (value, expiry)
        return True

    async def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def close(self):
        pass


class CacheManager:
    """Manages caching of Shopify API responses"""

    def __init__(self):
        self.ttl = settings.CACHE_TTL_SECONDS
        self._redis_client = None
        self._memory_cache = InMemoryCache()
        self._use_redis = REDIS_AVAILABLE and settings.REDIS_URL

    async def _get_redis(self):
        """Get or create Redis client"""
        if not self._use_redis:
            return None

        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self._redis_client.ping()
                logger.info("redis_connected")
            except Exception as e:
                logger.warning("redis_connection_failed", error=str(e))
                self._use_redis = False
                return None

        return self._redis_client

    def generate_key(self, store_id: str, query: str) -> str:
        """Generate a cache key from store ID and query"""
        # Normalize the query
        normalized_query = " ".join(query.split()).lower()

        # Create a hash of the query for shorter keys
        query_hash = hashlib.md5(normalized_query.encode()).hexdigest()[:12]

        return f"shopify:analytics:{store_id}:{query_hash}"

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a cached value.

        Args:
            key: The cache key

        Returns:
            The cached value or None if not found/expired
        """
        try:
            redis_client = await self._get_redis()

            if redis_client:
                value = await redis_client.get(key)
            else:
                value = await self._memory_cache.get(key)

            if value:
                logger.debug("cache_hit", key=key)
                return json.loads(value)

            logger.debug("cache_miss", key=key)
            return None

        except Exception as e:
            logger.error("cache_get_error", error=str(e), key=key)
            return None

    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a cached value.

        Args:
            key: The cache key
            value: The value to cache
            ttl: Optional TTL override in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            ttl = ttl or self.ttl
            serialized = json.dumps(value, default=str)

            redis_client = await self._get_redis()

            if redis_client:
                await redis_client.setex(key, ttl, serialized)
            else:
                await self._memory_cache.set(key, serialized, ttl)

            logger.debug("cache_set", key=key, ttl=ttl)
            return True

        except Exception as e:
            logger.error("cache_set_error", error=str(e), key=key)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cached value"""
        try:
            redis_client = await self._get_redis()

            if redis_client:
                await redis_client.delete(key)
            else:
                await self._memory_cache.delete(key)

            logger.debug("cache_deleted", key=key)
            return True

        except Exception as e:
            logger.error("cache_delete_error", error=str(e), key=key)
            return False

    async def invalidate_store(self, store_id: str) -> int:
        """
        Invalidate all cache entries for a store.

        Args:
            store_id: The store domain

        Returns:
            Number of keys deleted
        """
        try:
            redis_client = await self._get_redis()

            if redis_client:
                pattern = f"shopify:analytics:{store_id}:*"
                keys = []
                async for key in redis_client.scan_iter(match=pattern):
                    keys.append(key)

                if keys:
                    await redis_client.delete(*keys)

                logger.info("cache_invalidated", store_id=store_id, keys_deleted=len(keys))
                return len(keys)

            return 0

        except Exception as e:
            logger.error("cache_invalidate_error", error=str(e), store_id=store_id)
            return 0

    async def close(self):
        """Close the cache connection"""
        if self._redis_client:
            await self._redis_client.close()
        await self._memory_cache.close()
