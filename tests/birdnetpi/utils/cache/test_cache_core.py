"""Comprehensive tests for the main Cache class."""

import hashlib
from datetime import datetime
from unittest.mock import MagicMock, patch

from birdnetpi.utils.cache.cache import Cache, create_cache


class TestCacheInitialization:
    """Test Cache class initialization with different backends."""

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", True)
    @patch("birdnetpi.utils.cache.cache.MemcachedBackend")
    def test_init_with_memcached_success(self, mock_memcached_backend):
        """Test successful initialization with memcached backend."""
        mock_backend = MagicMock()
        mock_memcached_backend.return_value = mock_backend

        cache = Cache(
            memcached_host="localhost",
            memcached_port=11211,
            default_ttl=600,
            enable_cache_warming=True,
        )

        assert cache.default_ttl == 600
        assert cache.enable_cache_warming is True
        assert cache.backend_type == "memcached"
        assert cache._backend == mock_backend
        mock_memcached_backend.assert_called_once_with("localhost", 11211)

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", True)
    @patch("birdnetpi.utils.cache.cache.MemcachedBackend")
    @patch("birdnetpi.utils.cache.cache.InMemoryBackend")
    def test_init_memcached_fallback_to_memory(self, mock_memory_backend, mock_memcached_backend):
        """Test fallback to in-memory backend when memcached fails."""
        mock_memcached_backend.side_effect = Exception("Connection refused")
        mock_memory = MagicMock()
        mock_memory_backend.return_value = mock_memory

        cache = Cache()

        assert cache.backend_type == "memory"
        assert cache._backend == mock_memory
        mock_memory_backend.assert_called_once()

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", False)
    @patch("birdnetpi.utils.cache.cache.InMemoryBackend")
    def test_init_without_memcached(self, mock_memory_backend):
        """Test initialization when memcached is not available."""
        mock_memory = MagicMock()
        mock_memory_backend.return_value = mock_memory

        cache = Cache()

        assert cache.backend_type == "memory"
        assert cache._backend == mock_memory
        assert cache.default_ttl == 300
        assert cache.enable_cache_warming is True

    def test_init_statistics_tracking(self):
        """Test that statistics are initialized correctly."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            assert cache._stats == {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0,
            }


class TestCacheKeyGeneration:
    """Test cache key generation logic."""

    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            key = cache._generate_cache_key("test_namespace", param1="value1", param2="value2")

            # Should be consistent
            key2 = cache._generate_cache_key("test_namespace", param1="value1", param2="value2")
            assert key == key2

            # Should start with prefix
            assert key.startswith("birdnet_analytics:")

            # Should be a hash
            assert len(key.split(":")[1]) == 16  # 16 chars of SHA-256 hash

    def test_generate_cache_key_sorted_params(self):
        """Test that parameters are sorted for consistent key generation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            key1 = cache._generate_cache_key("namespace", z="value", a="value", m="value")
            key2 = cache._generate_cache_key("namespace", a="value", z="value", m="value")
            key3 = cache._generate_cache_key("namespace", m="value", a="value", z="value")

            assert key1 == key2 == key3

    def test_generate_cache_key_datetime_objects(self):
        """Test key generation with datetime objects."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            now = datetime(2025, 1, 15, 10, 30, 45)
            key = cache._generate_cache_key("namespace", timestamp=now)

            # Should use isoformat for datetime
            expected_parts = f"namespace|timestamp:{now.isoformat()}"
            expected_hash = hashlib.sha256(expected_parts.encode()).hexdigest()[:16]
            assert key == f"birdnet_analytics:{expected_hash}"

    def test_generate_cache_key_complex_types(self):
        """Test key generation with lists and dicts."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            # Test with list
            key1 = cache._generate_cache_key("namespace", items=[1, 2, 3])
            key2 = cache._generate_cache_key("namespace", items=[1, 2, 3])
            assert key1 == key2

            # Test with dict
            key3 = cache._generate_cache_key("namespace", config={"a": 1, "b": 2})
            key4 = cache._generate_cache_key("namespace", config={"b": 2, "a": 1})
            assert key3 == key4  # Dicts are sorted by json.dumps

    def test_generate_cache_key_none_values(self):
        """Test that None values are ignored in key generation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()

            key1 = cache._generate_cache_key("namespace", param1="value", param2=None)
            key2 = cache._generate_cache_key("namespace", param1="value")

            assert key1 == key2


class TestCacheGetSet:
    """Test cache get and set operations."""

    def test_get_cache_hit(self):
        """Test get operation with cache hit."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.get.return_value = "cached_value"

            cache = Cache()
            result = cache.get("namespace", param="value")

            assert result == "cached_value"
            assert cache._stats["hits"] == 1
            assert cache._stats["misses"] == 0
            mock_backend.get.assert_called_once()

    def test_get_cache_miss(self):
        """Test get operation with cache miss."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.get.return_value = None

            cache = Cache()
            result = cache.get("namespace", param="value")

            assert result is None
            assert cache._stats["hits"] == 0
            assert cache._stats["misses"] == 1

    def test_get_with_error(self):
        """Test get operation when backend raises error."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.get.side_effect = Exception("Backend error")

            cache = Cache()
            result = cache.get("namespace", param="value")

            assert result is None
            assert cache._stats["errors"] == 1

    def test_set_success(self):
        """Test successful set operation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.return_value = True

            cache = Cache(default_ttl=300)
            result = cache.set("namespace", "value", ttl=None, param="test")

            assert result is True
            assert cache._stats["sets"] == 1

            # Should use default TTL
            call_args = mock_backend.set.call_args
            assert call_args[0][1] == "value"  # Value
            assert call_args[0][2] == 300  # TTL

    def test_set_with_custom_ttl(self):
        """Test set operation with custom TTL."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.return_value = True

            cache = Cache(default_ttl=300)
            result = cache.set("namespace", "value", ttl=600, param="test")

            assert result is True

            # Should use custom TTL
            call_args = mock_backend.set.call_args
            assert call_args[0][2] == 600  # Custom TTL

    def test_set_failure(self):
        """Test set operation when backend returns False."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.return_value = False

            cache = Cache()
            result = cache.set("namespace", "value", param="test")

            assert result is False
            assert cache._stats["errors"] == 1

    def test_set_with_error(self):
        """Test set operation when backend raises error."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.side_effect = Exception("Backend error")

            cache = Cache()
            result = cache.set("namespace", "value", param="test")

            assert result is False
            assert cache._stats["errors"] == 1


class TestCacheDelete:
    """Test cache delete operations."""

    def test_delete_success(self):
        """Test successful delete operation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.delete.return_value = True

            cache = Cache()
            result = cache.delete("namespace", param="value")

            assert result is True
            assert cache._stats["deletes"] == 1

    def test_delete_failure(self):
        """Test delete operation when key doesn't exist."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.delete.return_value = False

            cache = Cache()
            result = cache.delete("namespace", param="value")

            assert result is False
            assert cache._stats["deletes"] == 0

    def test_delete_with_error(self):
        """Test delete operation when backend raises error."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.delete.side_effect = Exception("Backend error")

            cache = Cache()
            result = cache.delete("namespace", param="value")

            assert result is False
            assert cache._stats["errors"] == 1


class TestCacheExists:
    """Test cache exists operations."""

    def test_exists_true(self):
        """Test exists when key is present."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.return_value = True

            cache = Cache()
            result = cache.exists("namespace", param="value")

            assert result is True

    def test_exists_false(self):
        """Test exists when key is not present."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.return_value = False

            cache = Cache()
            result = cache.exists("namespace", param="value")

            assert result is False

    def test_exists_with_error(self):
        """Test exists when backend raises error."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.side_effect = Exception("Backend error")

            cache = Cache()
            result = cache.exists("namespace", param="value")

            assert result is False
            assert cache._stats["errors"] == 1


class TestCacheClear:
    """Test cache clear operations."""

    def test_clear_success(self):
        """Test successful clear operation."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.clear.return_value = True

            cache = Cache()
            # Set some stats
            cache._stats["hits"] = 10
            cache._stats["misses"] = 5

            result = cache.clear()

            assert result is True
            # Stats should be reset
            assert cache._stats["hits"] == 0
            assert cache._stats["misses"] == 0

    def test_clear_failure(self):
        """Test clear operation when backend fails."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.clear.side_effect = Exception("Backend error")

            cache = Cache()
            result = cache.clear()

            assert result is False
            assert cache._stats["errors"] == 1


class TestCacheInvalidatePattern:
    """Test pattern-based cache invalidation."""

    def test_invalidate_pattern(self):
        """Test that invalidate_pattern calls clear (simple implementation)."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.clear.return_value = True

            cache = Cache()
            result = cache.invalidate_pattern("namespace*")

            assert result is True
            mock_backend.clear.assert_called_once()


class TestCacheWarming:
    """Test cache warming functionality."""

    def test_warm_cache_enabled(self):
        """Test cache warming when enabled."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.return_value = False
            mock_backend.set.return_value = True

            cache = Cache(enable_cache_warming=True)

            # Define warming functions
            def func1(**kwargs):
                return "result1"

            def func2(**kwargs):
                return "result2"

            warming_functions = [
                ("namespace1", func1, {"param": "a"}, 300),
                ("namespace2", func2, {"param": "b"}, 600),
            ]

            results = cache.warm_cache(warming_functions)

            assert results == {"namespace1": True, "namespace2": True}
            assert mock_backend.set.call_count == 2

    def test_warm_cache_disabled(self):
        """Test cache warming when disabled."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend

            cache = Cache(enable_cache_warming=False)

            warming_functions = [
                ("namespace1", lambda: "result", {}, 300),
            ]

            results = cache.warm_cache(warming_functions)

            assert results == {}
            mock_backend.set.assert_not_called()

    def test_warm_cache_already_cached(self):
        """Test cache warming skips already cached items."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.return_value = True  # Already cached

            cache = Cache(enable_cache_warming=True)

            warming_functions = [
                ("namespace1", lambda: "result", {}, 300),
            ]

            results = cache.warm_cache(warming_functions)

            assert results == {"namespace1": True}
            mock_backend.set.assert_not_called()  # Should not set again

    def test_warm_cache_with_error(self):
        """Test cache warming handles errors gracefully."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.exists.return_value = False

            cache = Cache(enable_cache_warming=True)

            def failing_func(**kwargs):
                raise Exception("Function error")

            warming_functions = [
                ("namespace1", failing_func, {}, 300),
            ]

            results = cache.warm_cache(warming_functions)

            assert results == {"namespace1": False}


class TestCacheStatistics:
    """Test cache statistics functionality."""

    def test_get_stats_empty(self):
        """Test getting stats with no activity."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend"):
            cache = Cache()
            stats = cache.get_stats()

            assert stats == {
                "backend_type": "memory",
                "total_requests": 0,
                "hits": 0,
                "misses": 0,
                "hit_rate_percent": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0,
                "default_ttl": 300,
                "cache_warming_enabled": True,
            }

    def test_get_stats_with_activity(self):
        """Test getting stats after some cache activity."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend

            cache = Cache()

            # Simulate some activity
            cache._stats["hits"] = 75
            cache._stats["misses"] = 25
            cache._stats["sets"] = 50
            cache._stats["deletes"] = 10
            cache._stats["errors"] = 2

            stats = cache.get_stats()

            assert stats["total_requests"] == 100
            assert stats["hits"] == 75
            assert stats["misses"] == 25
            assert stats["hit_rate_percent"] == 75.0
            assert stats["sets"] == 50
            assert stats["deletes"] == 10
            assert stats["errors"] == 2


class TestCacheHealthCheck:
    """Test cache health check functionality."""

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", False)
    def test_health_check_healthy(self):
        """Test health check when cache is healthy."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend

            cache = Cache()

            # Make get return whatever was set (simulating a working cache)
            stored_values = {}

            def mock_set(key, value, ttl):
                stored_values[key] = value
                return True

            def mock_get(key):
                return stored_values.get(key)

            cache._backend.set = mock_set
            cache._backend.get = mock_get
            cache._backend.delete = lambda key: True

            health = cache.health_check()

            assert health["status"] == "healthy"
            assert health["backend"] == "memory"
            assert "stats" in health

    def test_health_check_set_failure(self):
        """Test health check when set operation fails."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.return_value = False

            cache = Cache()
            health = cache.health_check()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Set operation failed"

    def test_health_check_get_failure(self):
        """Test health check when get returns wrong value."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.return_value = True
            mock_backend.get.return_value = "wrong_value"

            cache = Cache()
            health = cache.health_check()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Get operation failed or data corrupted"

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", False)
    def test_health_check_delete_failure(self):
        """Test health check when delete fails (still reports healthy)."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend

            cache = Cache()

            # Make get return whatever was set (simulating a working cache)
            stored_values = {}

            def mock_set(key, value, ttl):
                stored_values[key] = value
                return True

            def mock_get(key):
                return stored_values.get(key)

            cache._backend.set = mock_set
            cache._backend.get = mock_get
            cache._backend.delete = lambda key: False

            health = cache.health_check()

            # Should still be healthy even if delete fails
            assert health["status"] == "healthy"

    def test_health_check_exception(self):
        """Test health check when exception is raised."""
        with patch("birdnetpi.utils.cache.cache.InMemoryBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            mock_backend.set.side_effect = Exception("Backend error")

            cache = Cache()
            health = cache.health_check()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Backend error"


class TestCreateCache:
    """Test the create_cache factory function."""

    def test_create_cache_default(self):
        """Test create_cache with default parameters."""
        with patch("birdnetpi.utils.cache.cache.Cache") as mock_cache:
            create_cache()

            mock_cache.assert_called_once_with(
                memcached_host="localhost",
                memcached_port=11211,
                default_ttl=300,
                enable_cache_warming=True,
            )

    def test_create_cache_custom(self):
        """Test create_cache with custom parameters."""
        with patch("birdnetpi.utils.cache.cache.Cache") as mock_cache:
            create_cache(
                memcached_host="192.168.1.100",
                memcached_port=11212,
                default_ttl=600,
                enable_cache_warming=False,
            )

            mock_cache.assert_called_once_with(
                memcached_host="192.168.1.100",
                memcached_port=11212,
                default_ttl=600,
                enable_cache_warming=False,
            )
