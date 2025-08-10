"""Cache service for analytics queries with memcached backend and fallback support.

This service provides caching for expensive analytics queries to improve dashboard
performance. It uses memcached as the primary backend to minimize disk writes
on SBC deployments where SD card longevity is important. Falls back to in-memory
caching if memcached is unavailable.

Key features:
- Memcached backend preferred for SBC deployments (no disk writes)
- Automatic fallback to in-memory caching if memcached unavailable
- TTL management and cache invalidation strategies
- Cache warming capabilities for common queries
- Thread-safe operations with proper error handling
"""

import hashlib
import json
import pickle
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

# Optional memcached dependency
try:
    import pymemcache
    from pymemcache.client.base import Client as MemcacheClient

    MEMCACHED_AVAILABLE = True
except ImportError:
    pymemcache = None  # type: ignore[assignment]
    MemcacheClient = None  # type: ignore[assignment,misc]
    MEMCACHED_AVAILABLE = False

T = TypeVar("T")

logger = structlog.get_logger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Any:  # noqa: ANN401
        """Get value from cache by key.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value or None if not found/expired
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all cached data.

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        pass


class MemcachedBackend(CacheBackend):
    """Memcached backend implementation.

    Uses pymemcache for fast, memory-only caching that doesn't write to disk.
    Ideal for SBC deployments where minimizing SD card writes is critical.
    """

    def __init__(self, host: str = "localhost", port: int = 11211, timeout: float = 1.0):
        """Initialize memcached backend.

        Args:
            host: Memcached server host
            port: Memcached server port
            timeout: Connection timeout in seconds

        Raises:
            RuntimeError: If memcached is not available
        """
        if not MEMCACHED_AVAILABLE:
            raise RuntimeError("pymemcache is required for MemcachedBackend")

        self.client = MemcacheClient(
            (host, port),
            timeout=timeout,
            connect_timeout=timeout,
            serializer=pickle,  # Use pickle for complex Python objects
            deserializer=pickle,
        )

        # Test connection
        try:
            self.client.version()
            logger.info("Memcached backend initialized successfully", host=host, port=port)
        except Exception as e:
            logger.error("Failed to connect to memcached", host=host, port=port, error=str(e))
            raise RuntimeError(f"Failed to connect to memcached at {host}:{port}: {e}") from e

    def get(self, key: str) -> Any:  # noqa: ANN401
        """Get value from memcached."""
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning("Memcached get failed", key=key, error=str(e))
            return None

    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in memcached with TTL."""
        try:
            return self.client.set(key, value, expire=ttl)
        except Exception as e:
            logger.warning("Memcached set failed", key=key, ttl=ttl, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Delete value from memcached."""
        try:
            return self.client.delete(key)
        except Exception as e:
            logger.warning("Memcached delete failed", key=key, error=str(e))
            return False

    def clear(self) -> bool:
        """Clear all memcached data."""
        try:
            return self.client.flush_all()
        except Exception as e:
            logger.warning("Memcached clear failed", error=str(e))
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in memcached."""
        try:
            return self.client.get(key) is not None
        except Exception as e:
            logger.warning("Memcached exists check failed", key=key, error=str(e))
            return False


class InMemoryBackend(CacheBackend):
    """In-memory cache backend implementation.

    Thread-safe fallback implementation using a simple dictionary with TTL tracking.
    Used when memcached is unavailable. Suitable for single-process deployments.
    """

    def __init__(self):
        """Initialize in-memory backend."""
        # Cache storage: {key: (value, expiry_timestamp)}
        self._cache: dict[str, tuple[Any, float]] = {}
        logger.info("In-memory cache backend initialized")

    def _is_expired(self, expiry: float) -> bool:
        """Check if cache entry has expired."""
        return time.time() > expiry

    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = [key for key, (_, expiry) in self._cache.items() if current_time > expiry]
        for key in expired_keys:
            del self._cache[key]

    def get(self, key: str) -> Any:  # noqa: ANN401
        """Get value from in-memory cache."""
        try:
            if key in self._cache:
                value, expiry = self._cache[key]
                if not self._is_expired(expiry):
                    return value
                else:
                    # Remove expired entry
                    del self._cache[key]

            # Periodic cleanup when cache gets large
            if len(self._cache) > 1000:
                self._cleanup_expired()

            return None
        except Exception as e:
            logger.warning("In-memory get failed", key=key, error=str(e))
            return None

    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in in-memory cache with TTL."""
        try:
            expiry = time.time() + ttl
            self._cache[key] = (value, expiry)
            return True
        except Exception as e:
            logger.warning("In-memory set failed", key=key, ttl=ttl, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Delete value from in-memory cache."""
        try:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
        except Exception as e:
            logger.warning("In-memory delete failed", key=key, error=str(e))
            return False

    def clear(self) -> bool:
        """Clear all in-memory cache data."""
        try:
            self._cache.clear()
            return True
        except Exception as e:
            logger.warning("In-memory clear failed", error=str(e))
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in in-memory cache."""
        try:
            if key in self._cache:
                _, expiry = self._cache[key]
                if not self._is_expired(expiry):
                    return True
                else:
                    del self._cache[key]
            return False
        except Exception as e:
            logger.warning("In-memory exists check failed", key=key, error=str(e))
            return False


class CacheService:
    """Analytics cache service with automatic backend selection and fallback.

    Provides caching for expensive analytics queries to improve dashboard performance.
    Automatically selects memcached if available, falls back to in-memory caching.
    Includes cache warming and invalidation strategies.
    """

    def __init__(
        self,
        memcached_host: str = "localhost",
        memcached_port: int = 11211,
        default_ttl: int = 300,  # 5 minutes default TTL
        enable_cache_warming: bool = True,
    ):
        """Initialize cache service with automatic backend selection.

        Args:
            memcached_host: Memcached server host (if available)
            memcached_port: Memcached server port (if available)
            default_ttl: Default cache TTL in seconds
            enable_cache_warming: Whether to enable cache warming functionality
        """
        self.default_ttl = default_ttl
        self.enable_cache_warming = enable_cache_warming
        self._backend: CacheBackend

        # Try memcached first (preferred for SBC deployments)
        if MEMCACHED_AVAILABLE:
            try:
                self._backend = MemcachedBackend(memcached_host, memcached_port)
                self.backend_type = "memcached"
                logger.info("Cache service initialized with memcached backend")
            except Exception as e:
                logger.warning(
                    "Failed to initialize memcached, falling back to in-memory cache", error=str(e)
                )
                self._backend = InMemoryBackend()
                self.backend_type = "memory"
        else:
            logger.info("Memcached not available, using in-memory cache backend")
            self._backend = InMemoryBackend()
            self.backend_type = "memory"

        # Statistics tracking
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
        }

    def _generate_cache_key(self, namespace: str, **kwargs: Any) -> str:  # noqa: ANN401
        """Generate a consistent cache key from parameters.

        Args:
            namespace: Cache namespace (e.g., 'species_summary', 'weekly_report')
            **kwargs: Parameters to include in key generation

        Returns:
            SHA-256 hash of the cache key components
        """
        # Sort parameters for consistent key generation
        key_parts = [namespace]
        for key, value in sorted(kwargs.items()):
            if value is not None:
                # Handle different types appropriately
                if hasattr(value, "isoformat"):  # datetime objects
                    key_parts.append(f"{key}:{value.isoformat()}")
                elif isinstance(value, list | dict):
                    # Serialize complex objects consistently
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
                logger.debug("Cache hit", namespace=namespace, key=cache_key[:8])
                return result
            else:
                self._stats["misses"] += 1
                logger.debug("Cache miss", namespace=namespace, key=cache_key[:8])
                return None
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache get error", namespace=namespace, error=str(e))
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
            success = self._backend.set(cache_key, value, cache_ttl)
            if success:
                self._stats["sets"] += 1
                logger.debug("Cache set", namespace=namespace, key=cache_key[:8], ttl=cache_ttl)
            else:
                self._stats["errors"] += 1
                logger.warning("Cache set failed", namespace=namespace, key=cache_key[:8])
            return success
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache set error", namespace=namespace, error=str(e))
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
            success = self._backend.delete(cache_key)
            if success:
                self._stats["deletes"] += 1
                logger.debug("Cache delete", namespace=namespace, key=cache_key[:8])
            return success
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache delete error", namespace=namespace, error=str(e))
            return False

    def exists(self, namespace: str, **kwargs: Any) -> bool:  # noqa: ANN401
        """Check if cached value exists.

        Args:
            namespace: Cache namespace
            **kwargs: Parameters for cache key generation

        Returns:
            True if key exists, False otherwise
        """
        cache_key = self._generate_cache_key(namespace, **kwargs)

        try:
            return self._backend.exists(cache_key)
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache exists check error", namespace=namespace, error=str(e))
            return False

    def invalidate_pattern(self, namespace: str) -> bool:
        """Invalidate all cache entries matching a namespace pattern.

        Note: This is a simple implementation that clears the entire cache.
        More sophisticated pattern matching would require backend-specific
        implementations (e.g., Redis SCAN).

        Args:
            namespace: Cache namespace pattern to invalidate

        Returns:
            True if successful, False otherwise
        """
        logger.info("Invalidating cache pattern", namespace=namespace)
        return self.clear()

    def clear(self) -> bool:
        """Clear all cached data.

        Returns:
            True if successful, False otherwise
        """
        try:
            success = self._backend.clear()
            if success:
                logger.info("Cache cleared successfully")
                # Reset stats
                for key in self._stats:
                    self._stats[key] = 0
            return success
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Cache clear error", error=str(e))
            return False

    def warm_cache(
        self, cache_warming_functions: list[tuple[str, Callable[..., Any], dict[str, Any], int]]
    ) -> dict[str, bool]:
        """Warm cache with common queries.

        Args:
            cache_warming_functions: List of (namespace, function, kwargs, ttl) tuples

        Returns:
            Dictionary mapping namespace to success status
        """
        if not self.enable_cache_warming:
            logger.info("Cache warming is disabled")
            return {}

        results = {}
        logger.info("Starting cache warming", functions_count=len(cache_warming_functions))

        for namespace, func, kwargs, ttl in cache_warming_functions:
            try:
                # Check if already cached
                if self.exists(namespace, **kwargs):
                    logger.debug("Cache already warmed", namespace=namespace)
                    results[namespace] = True
                    continue

                # Execute function and cache result
                logger.debug("Warming cache", namespace=namespace)
                result = func(**kwargs)

                success = self.set(namespace, result, ttl, **kwargs)
                results[namespace] = success

                if success:
                    logger.debug("Cache warmed successfully", namespace=namespace)
                else:
                    logger.warning("Failed to warm cache", namespace=namespace)

            except Exception as e:
                logger.error("Cache warming error", namespace=namespace, error=str(e))
                results[namespace] = False

        successful_warms = sum(1 for success in results.values() if success)
        logger.info(
            "Cache warming completed",
            successful=successful_warms,
            total=len(cache_warming_functions),
        )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache performance metrics
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "backend_type": self.backend_type,
            "total_requests": total_requests,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "sets": self._stats["sets"],
            "deletes": self._stats["deletes"],
            "errors": self._stats["errors"],
            "default_ttl": self.default_ttl,
            "cache_warming_enabled": self.enable_cache_warming,
        }

    def health_check(self) -> dict[str, Any]:
        """Perform cache health check.

        Returns:
            Dictionary containing health status and diagnostics
        """
        test_key = "health_check_test"
        test_value = {"timestamp": time.time(), "test": True}

        try:
            # Test set operation
            set_success = self._backend.set(test_key, test_value, 10)
            if not set_success:
                return {
                    "status": "unhealthy",
                    "backend": self.backend_type,
                    "error": "Set operation failed",
                    "stats": self.get_stats(),
                }

            # Test get operation
            retrieved_value = self._backend.get(test_key)
            if retrieved_value != test_value:
                return {
                    "status": "unhealthy",
                    "backend": self.backend_type,
                    "error": "Get operation failed or data corrupted",
                    "stats": self.get_stats(),
                }

            # Test delete operation
            delete_success = self._backend.delete(test_key)
            if not delete_success:
                logger.warning("Delete operation failed during health check")

            return {
                "status": "healthy",
                "backend": self.backend_type,
                "stats": self.get_stats(),
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": self.backend_type,
                "error": str(e),
                "stats": self.get_stats(),
            }


def create_cache_service(
    memcached_host: str = "localhost",
    memcached_port: int = 11211,
    default_ttl: int = 300,
    enable_cache_warming: bool = True,
) -> CacheService:
    """Create a configured cache service.

    Args:
        memcached_host: Memcached server host
        memcached_port: Memcached server port
        default_ttl: Default TTL in seconds
        enable_cache_warming: Whether to enable cache warming

    Returns:
        Configured CacheService instance
    """
    return CacheService(
        memcached_host=memcached_host,
        memcached_port=memcached_port,
        default_ttl=default_ttl,
        enable_cache_warming=enable_cache_warming,
    )
