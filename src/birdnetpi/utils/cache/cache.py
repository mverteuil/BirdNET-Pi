"""Core cache implementation using Redis backend.

This module provides the main Cache class that manages
caching for expensive operations using Redis as the backend.
"""

import hashlib
import json
import logging
from typing import Any

from birdnetpi.utils.cache.backends import CacheBackend, RedisBackend

logger = logging.getLogger(__name__)


class Cache:
    """Analytics cache using Redis backend.

    Provides caching for expensive analytics queries to improve dashboard performance.
    Uses Redis exclusively for caching with no fallback to ensure consistent behavior.
    Includes cache warming and invalidation strategies with pattern-based deletion support.

    This class was previously named CacheService but has been renamed to Cache
    for simplicity and clarity.
    """

    def __init__(
        self,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        redis_db: int = 0,
        default_ttl: int = 300,  # 5 minutes default TTL
        enable_cache_warming: bool = True,
    ):
        """Initialize cache with Redis backend.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            default_ttl: Default cache TTL in seconds
            enable_cache_warming: Whether to enable cache warming functionality

        Raises:
            RuntimeError: If Redis connection cannot be established
        """
        self.default_ttl = default_ttl
        self.enable_cache_warming = enable_cache_warming

        # Initialize Redis backend (will raise RuntimeError if connection fails)
        try:
            self._backend: CacheBackend = RedisBackend(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                timeout=1.0,
            )
            self.backend_type = "redis"
            logger.info("Cache initialized with Redis backend")
        except RuntimeError:
            # Re-raise RuntimeError from RedisBackend as-is
            raise
        except Exception as e:
            # Wrap other exceptions in RuntimeError
            raise RuntimeError(f"Failed to initialize Redis backend: {e}") from e

        # Statistics tracking
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "pattern_deletes": 0,
            "errors": 0,
        }

    def _generate_cache_key(self, namespace: str, **kwargs: Any) -> str:  # noqa: ANN401
        """Generate a consistent cache key from namespace and parameters.

        Args:
            namespace: Cache namespace
            **kwargs: Parameters to include in cache key

        Returns:
            Cache key string
        """
        # Sort kwargs for consistent key generation
        key_parts = [namespace]
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is not None:
                # Handle different value types
                if isinstance(value, (list, dict)):
                    key_parts.append(f"{key}:{json.dumps(value, sort_keys=True)}")
                else:
                    key_parts.append(f"{key}:{value!s}")

        cache_string = "|".join(key_parts)
        return f"birdnet_analytics:{hashlib.sha256(cache_string.encode()).hexdigest()[:16]}"

    def get(self, namespace: str, ttl: int | None = None, **kwargs: Any) -> Any:  # noqa: ANN401
        """Get cached value by namespace and parameters.

        Args:
            namespace: Cache namespace
            ttl: TTL for cache warming (not used for get operations)
            **kwargs: Parameters for cache key generation

        Returns:
            Cached value or None if not found
        """
        cache_key = self._generate_cache_key(namespace, **kwargs)

        try:
            result = self._backend.get(cache_key)
            if result is not None:
                self._stats["hits"] += 1
                logger.debug("Cache hit", extra={"namespace": namespace, "key": cache_key[:8]})
                return result
            else:
                self._stats["misses"] += 1
                logger.debug("Cache miss", extra={"namespace": namespace, "key": cache_key[:8]})
                return None
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache get error", extra={"namespace": namespace, "error": str(e)})
            return None

    def set(self, namespace: str, value: Any, ttl: int | None = None, **kwargs: Any) -> bool:  # noqa: ANN401
        """Set cached value with namespace and parameters.

        Args:
            namespace: Cache namespace
            value: Value to cache
            ttl: TTL in seconds (uses default if not specified)
            **kwargs: Parameters for cache key generation

        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(namespace, **kwargs)
        cache_ttl = ttl or self.default_ttl

        try:
            result = self._backend.set(cache_key, value, cache_ttl)
            if result:
                self._stats["sets"] += 1
                logger.debug(
                    "Cache set",
                    extra={
                        "namespace": namespace,
                        "key": cache_key[:8],
                        "ttl": cache_ttl,
                    },
                )
            return result
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache set error", extra={"namespace": namespace, "error": str(e)})
            return False

    def delete(self, namespace: str, **kwargs: Any) -> bool:  # noqa: ANN401
        """Delete cached value by namespace and parameters.

        Args:
            namespace: Cache namespace
            **kwargs: Parameters for cache key generation

        Returns:
            True if successful, False otherwise
        """
        cache_key = self._generate_cache_key(namespace, **kwargs)

        try:
            result = self._backend.delete(cache_key)
            if result:
                self._stats["deletes"] += 1
                logger.debug("Cache delete", extra={"namespace": namespace, "key": cache_key[:8]})
            return result
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache delete error", extra={"namespace": namespace, "error": str(e)})
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all cached values matching the given pattern.

        Uses Redis SCAN for efficient pattern-based deletion.

        Args:
            pattern: Redis pattern (e.g., "birdnet_analytics:*" or "*species*")

        Returns:
            Number of keys deleted
        """
        try:
            deleted = self._backend.delete_pattern(pattern)
            self._stats["pattern_deletes"] += deleted
            if deleted > 0:
                logger.debug(
                    "Cache pattern delete",
                    extra={"pattern": pattern, "deleted": deleted},
                )
            return deleted
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache pattern delete error", extra={"pattern": pattern, "error": str(e)})
            return 0

    def clear_namespace(self, namespace: str) -> int:
        """Clear all cached values for a namespace.

        Uses pattern matching to delete all keys in the namespace.

        Args:
            namespace: Cache namespace to clear

        Returns:
            Number of keys deleted
        """
        # Generate pattern for the namespace
        # Since we hash the full key, we can't easily clear by namespace prefix
        # This would require storing namespace info in the key itself
        # For now, we'll use a more general pattern
        pattern = f"birdnet_analytics:*{namespace}*"
        return self.delete_pattern(pattern)

    def ping(self) -> bool:
        """Test Redis connectivity.

        Returns:
            True if Redis is reachable, False otherwise
        """
        try:
            # For RedisBackend, we can access the client directly
            if hasattr(self._backend, "client"):
                return self._backend.client.ping()  # type: ignore[attr-defined]
            # Fallback: try a simple set/get operation
            test_key = "_health_check_ping"
            self._backend.set(test_key, "pong", ttl=1)
            return self._backend.get(test_key) == "pong"
        except Exception as e:
            logger.debug(f"Cache ping failed: {e}")
            return False

    def clear(self) -> bool:
        """Clear all cached data.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = self._backend.clear()
            if result:
                logger.info("Cache cleared")
                # Reset stats except errors
                errors = self._stats["errors"]
                self._stats = {
                    "hits": 0,
                    "misses": 0,
                    "sets": 0,
                    "deletes": 0,
                    "pattern_deletes": 0,
                    "errors": errors,
                }
            return result
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache clear error", extra={"error": str(e)})
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics including hit rate
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            **self._stats,
            "hit_rate": round(hit_rate * 100, 2),
            "total_requests": total_requests,
            "backend": self.backend_type,
        }

    def warm_cache(
        self,
        namespace: str,
        value_generator: callable,  # type: ignore[valid-type]
        ttl: int | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> bool:
        """Warm cache by generating and storing value.

        Useful for pre-populating cache with expensive computations.

        Args:
            namespace: Cache namespace
            value_generator: Callable that generates the value to cache
            ttl: TTL in seconds
            **kwargs: Parameters for cache key generation

        Returns:
            True if successful, False otherwise
        """
        if not self.enable_cache_warming:
            logger.debug("Cache warming disabled")
            return False

        try:
            value = value_generator()
            return self.set(namespace, value, ttl, **kwargs)
        except Exception as e:
            logger.error("Cache warming error", extra={"namespace": namespace, "error": str(e)})
            return False

    def __repr__(self) -> str:
        """Return string representation of Cache."""
        stats = self.get_stats()
        return (
            f"<Cache backend={self.backend_type} "
            f"hit_rate={stats['hit_rate']}% "
            f"requests={stats['total_requests']}>"
        )
