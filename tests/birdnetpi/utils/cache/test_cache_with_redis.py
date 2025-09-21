"""Tests for Cache class with Redis backend.

This module tests the actual cache operations using Redis.
Redis is the exclusive backend for caching in BirdNET-Pi.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import redis

from birdnetpi.utils.cache.backends import RedisBackend
from birdnetpi.utils.cache.cache import Cache


class TestCacheWithRedis:
    """Test Cache operations with Redis backend."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = MagicMock()
        mock_pool = MagicMock()

        with patch("birdnetpi.utils.cache.backends.redis.ConnectionPool") as mock_conn_pool:
            mock_conn_pool.return_value = mock_pool
            with patch("birdnetpi.utils.cache.backends.redis.Redis") as mock_redis:
                mock_redis.return_value = mock_client
                # Setup default return values
                mock_client.ping.return_value = True
                mock_client.get.return_value = None
                mock_client.setex.return_value = True
                mock_client.delete.return_value = 1
                mock_client.flushdb.return_value = True
                mock_client.exists.return_value = 0
                mock_client.scan_iter.return_value = []

                yield mock_client

    @pytest.fixture
    def cache_with_redis(self, mock_redis_client):
        """Create Cache instance with mocked Redis backend."""
        with patch("birdnetpi.utils.cache.backends.redis.ConnectionPool"):
            with patch(
                "birdnetpi.utils.cache.backends.redis.Redis", return_value=mock_redis_client
            ):
                cache = Cache(
                    redis_host="localhost",
                    redis_port=6379,
                    redis_db=0,
                    default_ttl=300,
                    enable_cache_warming=True,
                )
                return cache

    def test_redis_backend_initialization(self, mock_redis_client):
        """Should initialize Redis backend correctly."""
        with patch("birdnetpi.utils.cache.backends.redis.ConnectionPool"):
            with patch(
                "birdnetpi.utils.cache.backends.redis.Redis", return_value=mock_redis_client
            ):
                cache = Cache(
                    redis_host="localhost",
                    redis_port=6379,
                    redis_db=0,
                    default_ttl=300,
                )

                assert cache.backend_type == "redis"
                assert cache.default_ttl == 300
                assert cache.enable_cache_warming is True
                mock_redis_client.ping.assert_called()

    def test_cache_get_miss(self, cache_with_redis, mock_redis_client):
        """Should return None for cache miss."""
        mock_redis_client.get.return_value = None

        result = cache_with_redis.get("test_namespace", key1="value1", key2="value2")

        assert result is None
        assert cache_with_redis._stats["misses"] == 1
        assert cache_with_redis._stats["hits"] == 0

    def test_cache_get_hit(self, cache_with_redis, mock_redis_client):
        """Should return cached value for cache hit."""
        expected_data = {"result": "test_data"}
        mock_redis_client.get.return_value = json.dumps(expected_data).encode()

        result = cache_with_redis.get("test_namespace", key1="value1")

        assert result == expected_data
        assert cache_with_redis._stats["hits"] == 1
        assert cache_with_redis._stats["misses"] == 0

    def test_cache_set(self, cache_with_redis, mock_redis_client):
        """Should successfully set value in cache."""
        test_data = {"result": "test_data"}

        success = cache_with_redis.set("test_namespace", test_data, ttl=600, key1="value1")

        assert success is True
        assert cache_with_redis._stats["sets"] == 1
        # Verify setex was called with correct parameters
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][1] == 600  # TTL
        assert json.loads(call_args[0][2]) == test_data  # Data

    def test_cache_delete(self, cache_with_redis, mock_redis_client):
        """Should successfully delete cached value."""
        mock_redis_client.delete.return_value = 1

        success = cache_with_redis.delete("test_namespace", key1="value1")

        assert success is True
        assert cache_with_redis._stats["deletes"] == 1
        mock_redis_client.delete.assert_called_once()

    def test_cache_delete_pattern(self, cache_with_redis, mock_redis_client):
        """Should delete all values matching pattern."""
        # Mock scan_iter to return matching keys
        test_keys = [b"cache:key1", b"cache:key2", b"cache:key3"]
        mock_redis_client.scan_iter.return_value = test_keys
        mock_redis_client.delete.return_value = 1

        deleted = cache_with_redis.delete_pattern("cache:*")

        assert deleted == 3
        assert cache_with_redis._stats["pattern_deletes"] == 3
        mock_redis_client.scan_iter.assert_called_once_with(match="cache:*", count=100)
        assert mock_redis_client.delete.call_count == 3

    def test_cache_clear(self, cache_with_redis, mock_redis_client):
        """Should clear all cached data and reset stats."""
        # Set initial stats
        cache_with_redis._stats = {
            "hits": 10,
            "misses": 5,
            "sets": 8,
            "deletes": 3,
            "pattern_deletes": 2,
            "errors": 1,
        }

        success = cache_with_redis.clear()

        assert success is True
        mock_redis_client.flushdb.assert_called_once()
        # Check stats are reset except errors
        assert cache_with_redis._stats == {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "pattern_deletes": 0,
            "errors": 1,  # Errors preserved
        }

    def test_cache_warm_cache(self, cache_with_redis, mock_redis_client):
        """Should warm cache by pre-generating values."""
        test_data = {"warmed": "data"}

        def value_generator():
            return test_data

        success = cache_with_redis.warm_cache(
            "test_namespace", value_generator, ttl=1200, key1="value1"
        )

        assert success is True
        assert cache_with_redis._stats["sets"] == 1

    def test_cache_warm_cache_disabled(self, cache_with_redis):
        """Should skip cache warming when disabled."""
        cache_with_redis.enable_cache_warming = False

        def value_generator():
            return {"data": "value"}

        success = cache_with_redis.warm_cache("test_namespace", value_generator)

        assert success is False

    def test_cache_stats(self, cache_with_redis):
        """Should retrieve accurate cache statistics."""
        cache_with_redis._stats = {
            "hits": 50,
            "misses": 10,
            "sets": 30,
            "deletes": 5,
            "pattern_deletes": 2,
            "errors": 1,
        }

        stats = cache_with_redis.get_stats()

        assert stats["hits"] == 50
        assert stats["misses"] == 10
        assert stats["hit_rate"] == 83.33  # 50 / (50 + 10) * 100
        assert stats["total_requests"] == 60
        assert stats["backend"] == "redis"

    def test_cache_error_handling(self, cache_with_redis, mock_redis_client):
        """Should handle Redis errors gracefully."""
        # Simulate Redis error
        mock_redis_client.get.side_effect = redis.RedisError("Connection lost")

        result = cache_with_redis.get("test_namespace", key1="value1")

        assert result is None
        assert cache_with_redis._stats["errors"] == 1

    def test_cache_key_generation(self, cache_with_redis):
        """Should generate consistent cache keys regardless of parameter order."""
        key1 = cache_with_redis._generate_cache_key(
            "namespace", param1="value1", param2=123, param3=["a", "b"]
        )

        key2 = cache_with_redis._generate_cache_key(
            "namespace", param3=["a", "b"], param1="value1", param2=123
        )

        # Keys should be identical regardless of parameter order
        assert key1 == key2
        assert key1.startswith("birdnet_analytics:")

    def test_redis_backend_connection_retry(self):
        """Should retry connection on initial failures."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = [
            redis.ConnectionError("Failed"),
            redis.ConnectionError("Failed"),
            True,  # Success on third attempt
        ]

        with patch("birdnetpi.utils.cache.backends.redis.ConnectionPool"):
            with patch("birdnetpi.utils.cache.backends.redis.Redis", return_value=mock_client):
                with patch("time.sleep"):  # Patch time.sleep globally
                    RedisBackend(host="localhost", port=6379)
                    assert mock_client.ping.call_count == 3

    def test_redis_backend_connection_failure(self):
        """Should raise RuntimeError after max connection retries."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Failed")

        with patch("birdnetpi.utils.cache.backends.redis.ConnectionPool"):
            with patch("birdnetpi.utils.cache.backends.redis.Redis", return_value=mock_client):
                with patch("time.sleep"):  # Patch time.sleep globally
                    with pytest.raises(RuntimeError) as exc_info:
                        RedisBackend(host="localhost", port=6379)

                    assert "Failed to connect to Redis" in str(exc_info.value)
                    assert mock_client.ping.call_count == 3
