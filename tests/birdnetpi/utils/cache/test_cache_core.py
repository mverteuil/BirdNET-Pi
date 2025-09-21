"""Core tests for Cache class initialization.

This module tests the Cache class's initialization with Redis backend.
Redis is the exclusive backend for caching in BirdNET-Pi.
"""

from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.utils.cache.cache import Cache


class TestCacheInitialization:
    """Should test Cache class initialization with Redis backend."""

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_with_redis_success(self, mock_redis, mock_pool):
        """Should successfully initialize with Redis backend."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            default_ttl=600,
            enable_cache_warming=True,
        )

        assert cache.default_ttl == 600
        assert cache.enable_cache_warming is True
        assert cache.backend_type == "redis"
        mock_client.ping.assert_called()

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_redis_connection_failure(self, mock_redis, mock_pool):
        """Should raise RuntimeError when Redis is unavailable."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        # Simulate connection failure on all retries
        mock_client.ping.side_effect = Exception("Connection refused")

        with pytest.raises(RuntimeError) as exc_info:
            Cache(
                redis_host="localhost",
                redis_port=6379,
                redis_db=0,
            )

        # The error message could be either format depending on the exception
        error_msg = str(exc_info.value)
        assert "Failed to" in error_msg and ("Redis" in error_msg or "backend" in error_msg)

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_with_default_parameters(self, mock_redis, mock_pool):
        """Should initialize with default parameters."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache()

        assert cache.default_ttl == 300
        assert cache.enable_cache_warming is True
        assert cache.backend_type == "redis"

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_statistics_tracking(self, mock_redis, mock_pool):
        """Should initialize statistics correctly."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache()

        assert cache._stats == {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "pattern_deletes": 0,
            "errors": 0,
        }

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_with_custom_ttl(self, mock_redis, mock_pool):
        """Should initialize with custom TTL."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache(default_ttl=1800)

        assert cache.default_ttl == 1800

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_init_with_cache_warming_disabled(self, mock_redis, mock_pool):
        """Should initialize with cache warming disabled."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache(enable_cache_warming=False)

        assert cache.enable_cache_warming is False

    @patch("birdnetpi.utils.cache.backends.redis.ConnectionPool")
    @patch("birdnetpi.utils.cache.backends.redis.Redis")
    def test_repr_method(self, mock_redis, mock_pool):
        """Should provide informative string representation."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = Cache()
        cache._stats = {"hits": 50, "misses": 10}

        repr_str = repr(cache)

        assert "<Cache backend=redis" in repr_str
        assert "hit_rate=83.33%" in repr_str
        assert "requests=60>" in repr_str
