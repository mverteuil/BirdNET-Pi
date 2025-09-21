"""Cache backend implementations for the cache system.

This module provides the Redis backend implementation for caching.
Redis is used in memory-only mode for fast, distributed caching without disk writes.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import redis

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

    @abstractmethod
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching the given pattern.

        Args:
            pattern: Pattern to match keys (e.g., "cache:prefix:*")

        Returns:
            Number of keys deleted
        """
        pass


class RedisBackend(CacheBackend):
    """Redis backend implementation.

    Uses Redis in memory-only mode for fast caching without disk writes.
    Ideal for SBC deployments where minimizing SD card writes is critical.
    Supports pattern-based key deletion for efficient cache invalidation.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        db: int = 0,
        timeout: float = 1.0,
        decode_responses: bool = False,
    ):
        """Initialize Redis backend.

        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            timeout: Connection timeout in seconds
            decode_responses: Whether to decode responses to strings

        Raises:
            RuntimeError: If Redis connection cannot be established
        """
        self.host = host
        self.port = port
        self.db = db

        try:
            # Create Redis connection pool for efficiency
            self.pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
                decode_responses=decode_responses,
            )
            self.client = redis.Redis(connection_pool=self.pool)

            # Test connection with retries for startup timing
            max_retries = 3
            retry_delay = 0.5
            import time

            for attempt in range(max_retries):
                try:
                    self.client.ping()
                    logger.debug(
                        "Redis backend initialized successfully",
                        extra={"host": host, "port": port, "db": db},
                    )
                    break
                except redis.ConnectionError as e:
                    if attempt < max_retries - 1:
                        logger.debug(
                            f"Redis connection attempt {attempt + 1} failed, retrying...",
                            extra={"error": str(e)},
                        )
                        time.sleep(retry_delay)
                    else:
                        raise RuntimeError(
                            f"Failed to connect to Redis at {host}:{port} "
                            f"after {max_retries} attempts"
                        ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Redis backend: {e}") from e

    def get(self, key: str) -> Any:  # noqa: ANN401
        """Get value from cache by key.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value or None if not found/expired
        """
        try:
            value = self.client.get(key)
            if value is None:
                return None

            # Try to deserialize JSON
            try:
                return json.loads(value)  # type: ignore[arg-type]
            except (json.JSONDecodeError, TypeError):
                # Return as-is if not JSON
                return value.decode("utf-8") if isinstance(value, bytes) else value
        except redis.RedisError as e:
            logger.error(f"Redis get error for key '{key}': {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def set(self, key: str, value: Any, ttl: int) -> bool:  # noqa: ANN401
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize value to JSON for consistency
            if isinstance(value, (str, bytes)):
                serialized = value
            else:
                serialized = json.dumps(value)

            # Set with expiration
            return bool(self.client.setex(key, ttl, serialized))
        except (redis.RedisError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"Redis set error for key '{key}': {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if successful (or key didn't exist), False on error
        """
        try:
            self.client.delete(key)
            return True
        except redis.RedisError as e:
            logger.error(f"Redis delete error for key '{key}': {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def clear(self) -> bool:
        """Clear all cached data in the current database.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.flushdb()
            return True
        except redis.RedisError as e:
            logger.error(f"Redis clear error: {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(self.client.exists(key))
        except redis.RedisError as e:
            logger.error(f"Redis exists error for key '{key}': {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching the given pattern.

        Uses SCAN for efficient iteration without blocking the server.

        Args:
            pattern: Pattern to match keys (e.g., "cache:prefix:*")

        Returns:
            Number of keys deleted
        """
        try:
            deleted_count = 0
            # Use SCAN to find matching keys without blocking
            for key in self.client.scan_iter(match=pattern, count=100):
                if self.client.delete(key):
                    deleted_count += 1

            logger.debug(f"Deleted {deleted_count} keys matching pattern '{pattern}'")
            return deleted_count
        except redis.RedisError as e:
            logger.error(f"Redis delete_pattern error for pattern '{pattern}': {e}")
            raise  # Re-raise to let cache layer handle and count errors

    def __del__(self):
        """Clean up Redis connection pool on deletion."""
        if hasattr(self, "pool"):
            try:
                self.pool.disconnect()
            except Exception:
                pass  # Ignore errors during cleanup
