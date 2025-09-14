"""Tests for Cache class using MemcachedBackend.

These tests verify Cache functionality when using the real MemcachedBackend.
Tests are skipped if pymemcache is not installed or memcached is not running.
"""

import hashlib
from datetime import datetime

import pytest

from birdnetpi.utils.cache.backends import MEMCACHED_AVAILABLE
from birdnetpi.utils.cache.cache import Cache

# Skip entire module if memcached isn't available
pytestmark = pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")


@pytest.fixture(autouse=True, scope="module")
def require_memcached_running():
    """Ensure memcached is actually running."""
    if MEMCACHED_AVAILABLE:
        try:
            # Try to create a cache - will fail if memcached not running
            cache = Cache()
            if cache.backend_type != "memcached":
                pytest.skip("Memcached not running")
            # Clear any existing data to ensure clean state
            cache.clear()
        except Exception as e:
            pytest.skip(f"Memcached not available or not running: {e}")


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test to ensure isolation."""
    cache = Cache()
    cache.clear()
    yield
    cache.clear()


class TestCacheKeyGeneration:
    """Test cache key generation logic with memcached backend."""

    def test_generate_cache_key_basic(self):
        """Should basic cache key generation."""
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
        """Should parameters are sorted for consistent key generation."""
        cache = Cache()

        key1 = cache._generate_cache_key("namespace", z="value", a="value", m="value")
        key2 = cache._generate_cache_key("namespace", a="value", z="value", m="value")
        key3 = cache._generate_cache_key("namespace", m="value", a="value", z="value")

        assert key1 == key2 == key3

    def test_generate_cache_key_datetime_objects(self):
        """Should key generation with datetime objects."""
        cache = Cache()

        now = datetime(2025, 1, 15, 10, 30, 45)
        key = cache._generate_cache_key("namespace", timestamp=now)

        # Should use isoformat for datetime
        expected_parts = f"namespace|timestamp:{now.isoformat()}"
        expected_hash = hashlib.sha256(expected_parts.encode()).hexdigest()[:16]
        assert key == f"birdnet_analytics:{expected_hash}"

    def test_generate_cache_key_complex_types(self):
        """Should key generation with lists and dicts."""
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
        """Should none values are ignored in key generation."""
        cache = Cache()

        key1 = cache._generate_cache_key("namespace", param1="value", param2=None)
        key2 = cache._generate_cache_key("namespace", param1="value")

        assert key1 == key2


class TestCacheGetSet:
    """Test cache get and set operations with memcached."""

    def test_get_cache_hit(self):
        """Should get operation with cache hit."""
        cache = Cache()

        # Set a value first
        cache.set("namespace", "cached_value", param="value")

        # Get it back
        result = cache.get("namespace", param="value")

        assert result == "cached_value"
        assert cache._stats["hits"] == 1
        assert cache._stats["misses"] == 0

    def test_get_cache_miss(self):
        """Should get operation with cache miss."""
        cache = Cache()

        result = cache.get("namespace", param="value")

        assert result is None
        assert cache._stats["hits"] == 0
        assert cache._stats["misses"] == 1

    def test_set_success(self):
        """Should successful set operation."""
        cache = Cache(default_ttl=300)

        result = cache.set("namespace", "value", ttl=None, param="test")

        assert result is True
        assert cache._stats["sets"] == 1

        # Verify the value was actually stored
        stored = cache.get("namespace", param="test")
        assert stored == "value"

    def test_set_with_custom_ttl(self):
        """Should set operation with custom TTL."""
        cache = Cache(default_ttl=300)

        result = cache.set("namespace", "value", ttl=600, param="test")

        assert result is True

        # Verify the value was stored
        stored = cache.get("namespace", param="test")
        assert stored == "value"

    def test_set_complex_data(self):
        """Should setting complex data structures with memcached."""
        cache = Cache()

        complex_data = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "tuple": (4, 5, 6),
            "string": "test",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }

        result = cache.set("namespace", complex_data, param="complex")
        assert result is True

        # Verify the data round-trips correctly through pickle serialization
        stored = cache.get("namespace", param="complex")
        assert stored == complex_data


class TestCacheDelete:
    """Test cache delete operations with memcached."""

    def test_delete_success(self):
        """Should successful delete operation."""
        cache = Cache()

        # Set a value first
        cache.set("namespace", "value", param="test")

        # Delete it
        result = cache.delete("namespace", param="test")

        assert result is True
        assert cache._stats["deletes"] == 1

        # Verify it's gone
        assert cache.get("namespace", param="test") is None

    def test_delete_nonexistent(self):
        """Should delete operation when key doesn't exist."""
        cache = Cache()

        result = cache.delete("namespace", param="nonexistent")

        # Memcached returns True even for non-existent keys (idempotent operation)
        assert result is True
        assert cache._stats["deletes"] == 1


class TestCacheExists:
    """Test cache exists operations with memcached."""

    def test_exists_true(self):
        """Should exists when key is present."""
        cache = Cache()

        # Set a value
        cache.set("namespace", "value", param="test")

        result = cache.exists("namespace", param="test")

        assert result is True

    def test_exists_false(self):
        """Should exists when key is not present."""
        cache = Cache()

        result = cache.exists("namespace", param="nonexistent")

        assert result is False


class TestCacheClear:
    """Test cache clear operations with memcached."""

    def test_clear_success(self):
        """Should successful clear operation."""
        cache = Cache()

        # Set some values and stats
        cache.set("namespace1", "value1", param="test1")
        cache.set("namespace2", "value2", param="test2")
        cache._stats["hits"] = 10
        cache._stats["misses"] = 5

        result = cache.clear()

        assert result is True
        # Stats should be reset
        assert cache._stats["hits"] == 0
        assert cache._stats["misses"] == 0

        # Values should be gone
        assert cache.get("namespace1", param="test1") is None
        assert cache.get("namespace2", param="test2") is None


class TestCacheInvalidatePattern:
    """Test pattern-based cache invalidation with memcached."""

    def test_invalidate_pattern(self):
        """Should invalidate_pattern calls clear (simple implementation)."""
        cache = Cache()

        # Set some values
        cache.set("namespace1", "value1")
        cache.set("namespace2", "value2")

        result = cache.invalidate_pattern("namespace*")

        assert result is True
        # Should clear everything (simple implementation)
        assert cache.get("namespace1") is None
        assert cache.get("namespace2") is None


class TestCacheWarming:
    """Test cache warming functionality with memcached."""

    def test_warm_cache_enabled(self):
        """Should cache warming when enabled."""
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

        # Verify values were cached
        assert cache.get("namespace1", param="a") == "result1"
        assert cache.get("namespace2", param="b") == "result2"

    def test_warm_cache_disabled(self):
        """Should cache warming when disabled."""
        cache = Cache(enable_cache_warming=False)

        warming_functions = [
            ("namespace1", lambda: "result", {}, 300),
        ]

        results = cache.warm_cache(warming_functions)

        assert results == {}
        # Nothing should be cached
        assert cache.get("namespace1") is None

    def test_warm_cache_already_cached(self):
        """Should cache warming skips already cached items."""
        cache = Cache(enable_cache_warming=True)

        # Pre-cache a value
        cache.set("namespace1", "existing", param="a")

        warming_functions = [
            ("namespace1", lambda **kwargs: "new_value", {"param": "a"}, 300),
        ]

        results = cache.warm_cache(warming_functions)

        assert results == {"namespace1": True}
        # Should keep existing value
        assert cache.get("namespace1", param="a") == "existing"

    def test_warm_cache_with_error(self):
        """Should cache warming handles errors gracefully."""
        cache = Cache(enable_cache_warming=True)

        def failing_func(**kwargs):
            raise Exception("Function error")

        warming_functions = [
            ("namespace1", failing_func, {}, 300),
        ]

        results = cache.warm_cache(warming_functions)

        assert results == {"namespace1": False}
        # Nothing should be cached
        assert cache.get("namespace1") is None


class TestCacheStatistics:
    """Test cache statistics functionality with memcached."""

    def test_get_stats_empty(self):
        """Should getting stats with no activity."""
        cache = Cache()
        stats = cache.get_stats()

        assert stats == {
            "backend_type": "memcached",
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
        """Should getting stats after some cache activity."""
        cache = Cache()

        # Simulate some activity
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # hit
        cache.get("key2")  # hit
        cache.get("key3")  # miss
        cache.delete("key1")

        stats = cache.get_stats()

        assert stats["total_requests"] == 3
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 66.67
        assert stats["sets"] == 2
        assert stats["deletes"] == 1


class TestCacheHealthCheck:
    """Test cache health check functionality with memcached."""

    def test_health_check_healthy(self):
        """Should health check when cache is healthy."""
        cache = Cache()

        health = cache.health_check()

        assert health["status"] == "healthy"
        assert health["backend"] == "memcached"
        assert "stats" in health


class TestMemcachedSpecific:
    """Tests specific to memcached backend behavior."""

    def test_large_value_handling(self):
        """Should handling of large values (memcached has size limits)."""
        cache = Cache()

        # Create a large value (but within typical memcached limits)
        large_value = "x" * (1024 * 512)  # 512KB

        result = cache.set("namespace", large_value, param="large")
        assert result is True

        stored = cache.get("namespace", param="large")
        assert stored == large_value

    def test_key_expiration(self):
        """Should keys actually expire with TTL."""
        import time

        cache = Cache()

        # Set with very short TTL
        cache.set("namespace", "value", ttl=1, param="expire")

        # Should exist immediately
        assert cache.get("namespace", param="expire") == "value"

        # Wait for expiration
        time.sleep(1.5)

        # Should be gone
        assert cache.get("namespace", param="expire") is None

    def test_concurrent_access(self):
        """Should multiple cache instances can share data via memcached."""
        cache1 = Cache()
        cache2 = Cache()

        # Set in one instance
        cache1.set("shared", "data", param="test")

        # Get from another instance
        result = cache2.get("shared", param="test")

        assert result == "data"
