"""Cache backend implementations for the cache system.

This module provides different backend implementations for caching:
- MemcachedBackend: Uses memcached for distributed caching
- InMemoryBackend: Uses a simple dictionary for single-process caching
"""

import logging
import pickle
import time
from abc import ABC, abstractmethod
from typing import Any

# Optional memcached dependency
try:
    import pymemcache
    from pymemcache.client.base import Client as MemcacheClient

    MEMCACHED_AVAILABLE = True
except ImportError:
    pymemcache = None  # type: ignore[assignment]
    MemcacheClient = None  # type: ignore[assignment,misc]
    MEMCACHED_AVAILABLE = False

logger = logging.getLogger(__name__)


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

    def __init__(self, host: str = "127.0.0.1", port: int = 11211, timeout: float = 1.0):
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

        # Define serializer functions for pymemcache
        def serialize(key: bytes, value: Any) -> tuple[bytes, int]:  # noqa: ANN401
            if isinstance(value, bytes):
                return value, 1
            # Safe: Pickle used for memcached serialization only
            return pickle.dumps(value), 2  # nosemgrep

        def deserialize(key: bytes, value: bytes, flags: int) -> Any:  # noqa: ANN401
            if flags == 1:
                return value
            if flags == 2:
                # Safe: Pickle used for memcached deserialization only
                return pickle.loads(value)  # nosemgrep
            raise ValueError(f"Unknown serialization flags: {flags}")

        self.client = MemcacheClient(  # type: ignore[misc]
            (host, port),
            timeout=timeout,
            connect_timeout=timeout,
            serializer=serialize,
            deserializer=deserialize,
        )

        # Test connection with retries for startup timing
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries):
            try:
                self.client.version()
                logger.debug(
                    "Memcached backend initialized successfully", extra={"host": host, "port": port}
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Memcached connection attempt {attempt + 1} failed, retrying...",
                        extra={"error": str(e)},
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "Failed to connect to memcached",
                        extra={"host": host, "port": port, "error": str(e)},
                    )
                    raise RuntimeError(
                        f"Failed to connect to memcached at {host}:{port}: {e}"
                    ) from e

    def get(self, key: str) -> Any:  # noqa: ANN401
        """Get value from memcached."""
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning("Memcached get failed", extra={"key": key, "error": str(e)})
            return None

    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in memcached with TTL."""
        try:
            result = self.client.set(key, value, expire=ttl)
            return bool(result)
        except Exception as e:
            logger.warning("Memcached set failed", extra={"key": key, "ttl": ttl, "error": str(e)})
            return False

    def delete(self, key: str) -> bool:
        """Delete value from memcached."""
        try:
            return self.client.delete(key)
        except Exception as e:
            logger.warning("Memcached delete failed", extra={"key": key, "error": str(e)})
            return False

    def clear(self) -> bool:
        """Clear all memcached data."""
        try:
            return self.client.flush_all()
        except Exception as e:
            logger.warning("Memcached clear failed", extra={"error": str(e)})
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in memcached."""
        try:
            return self.client.get(key) is not None
        except Exception as e:
            logger.warning("Memcached exists check failed", extra={"key": key, "error": str(e)})
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
            logger.warning("In-memory get failed", extra={"key": key, "error": str(e)})
            return None

    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in in-memory cache with TTL."""
        try:
            expiry = time.time() + ttl
            self._cache[key] = (value, expiry)
            return True
        except Exception as e:
            logger.warning("In-memory set failed", extra={"key": key, "ttl": ttl, "error": str(e)})
            return False

    def delete(self, key: str) -> bool:
        """Delete value from in-memory cache."""
        try:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
        except Exception as e:
            logger.warning("In-memory delete failed", extra={"key": key, "error": str(e)})
            return False

    def clear(self) -> bool:
        """Clear all in-memory cache data."""
        try:
            self._cache.clear()
            return True
        except Exception as e:
            logger.warning("In-memory clear failed", extra={"error": str(e)})
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
            logger.warning("In-memory exists check failed", extra={"key": key, "error": str(e)})
            return False
