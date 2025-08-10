"""Tests for the cache service for analytics queries."""

import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from birdnetpi.services.cache_service import (
    MEMCACHED_AVAILABLE,
    CacheService,
    InMemoryBackend,
    MemcachedBackend,
    create_cache_service,
)


class TestInMemoryBackend:
    """Test the in-memory cache backend."""

    def test_init(self):
        """Test backend initialization."""
        backend = InMemoryBackend()
        assert backend._cache == {}

    def test_set_and_get(self):
        """Test basic set and get operations."""
        backend = InMemoryBackend()

        # Test successful set and get
        assert backend.set("key1", "value1", 60) is True
        assert backend.get("key1") == "value1"

        # Test get non-existent key
        assert backend.get("non_existent") is None

    def test_ttl_expiration(self):
        """Test TTL expiration functionality."""
        backend = InMemoryBackend()

        # Set with very short TTL
        backend.set("expire_key", "expire_value", 1)
        assert backend.get("expire_key") == "expire_value"

        # Wait for expiration
        time.sleep(1.1)
        assert backend.get("expire_key") is None

    def test_delete(self):
        """Test delete operation."""
        backend = InMemoryBackend()

        # Set and delete
        backend.set("delete_key", "delete_value", 60)
        assert backend.get("delete_key") == "delete_value"
        assert backend.delete("delete_key") is True
        assert backend.get("delete_key") is None

        # Delete non-existent key
        assert backend.delete("non_existent") is False

    def test_exists(self):
        """Test exists operation."""
        backend = InMemoryBackend()

        # Check non-existent key
        assert backend.exists("non_existent") is False

        # Set and check
        backend.set("exists_key", "exists_value", 60)
        assert backend.exists("exists_key") is True

        # Check expired key
        backend.set("expire_key", "expire_value", 1)
        time.sleep(1.1)
        assert backend.exists("expire_key") is False

    def test_clear(self):
        """Test clear operation."""
        backend = InMemoryBackend()

        # Set multiple keys
        backend.set("key1", "value1", 60)
        backend.set("key2", "value2", 60)

        # Clear and verify
        assert backend.clear() is True
        assert backend.get("key1") is None
        assert backend.get("key2") is None

    def test_cleanup_expired(self):
        """Test expired entry cleanup."""
        backend = InMemoryBackend()

        # Set multiple keys with different TTL
        backend.set("keep", "value1", 60)
        backend.set("expire", "value2", 1)

        time.sleep(1.1)

        # Getting expired key should remove it
        result = backend.get("expire")
        assert result is None
        assert "expire" not in backend._cache
        assert "keep" in backend._cache

    def test_error_handling(self):
        """Test error handling in operations."""
        backend = InMemoryBackend()

        # Mock an error condition by setting _cache to a non-dict
        backend._cache = "invalid_cache_type"  # type: ignore[assignment]

        assert backend.get("key") is None
        assert backend.set("key", "value", 60) is False
        assert backend.delete("key") is False
        assert backend.exists("key") is False
        assert backend.clear() is False


@pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not available")
class TestMemcachedBackend:
    """Test the memcached backend (only if pymemcache is available)."""

    def test_init_success(self):
        """Test successful memcached backend initialization."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.return_value = "1.6.0"
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)
            assert backend.client == mock_instance
            mock_instance.version.assert_called_once()

    def test_init_failure(self):
        """Test memcached backend initialization failure."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.side_effect = Exception("Connection failed")
            mock_client.return_value = mock_instance

            with pytest.raises(RuntimeError, match="Failed to connect to memcached"):
                MemcachedBackend("localhost", 11211)

    def test_operations_with_mock(self):
        """Test memcached operations with mocked client."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.return_value = "1.6.0"
            mock_instance.get.return_value = "test_value"
            mock_instance.set.return_value = True
            mock_instance.delete.return_value = True
            mock_instance.flush_all.return_value = True
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Test operations
            assert backend.get("test_key") == "test_value"
            assert backend.set("test_key", "test_value", 60) is True
            assert backend.delete("test_key") is True
            assert backend.clear() is True
            assert backend.exists("test_key") is True

    def test_error_handling_with_mock(self):
        """Test memcached error handling with mocked client."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.return_value = "1.6.0"
            mock_instance.get.side_effect = Exception("Get error")
            mock_instance.set.side_effect = Exception("Set error")
            mock_instance.delete.side_effect = Exception("Delete error")
            mock_instance.flush_all.side_effect = Exception("Clear error")
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Test error handling
            assert backend.get("test_key") is None
            assert backend.set("test_key", "test_value", 60) is False
            assert backend.delete("test_key") is False
            assert backend.clear() is False
            assert backend.exists("test_key") is False


class TestCacheService:
    """Test the main cache service."""

    def test_init_memory_backend(self):
        """Test initialization with memory backend."""
        with patch("birdnetpi.services.cache_service.MEMCACHED_AVAILABLE", False):
            cache = CacheService()
            assert cache.backend_type == "memory"
            assert isinstance(cache._backend, InMemoryBackend)

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not available")
    def test_init_memcached_backend_success(self):
        """Test initialization with successful memcached backend."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.return_value = "1.6.0"
            mock_client.return_value = mock_instance

            cache = CacheService()
            assert cache.backend_type == "memcached"
            assert isinstance(cache._backend, MemcachedBackend)

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not available")
    def test_init_memcached_fallback(self):
        """Test fallback to memory when memcached fails."""
        with patch("birdnetpi.services.cache_service.MemcacheClient") as mock_client:
            mock_instance = Mock()
            mock_instance.version.side_effect = Exception("Connection failed")
            mock_client.return_value = mock_instance

            cache = CacheService()
            assert cache.backend_type == "memory"
            assert isinstance(cache._backend, InMemoryBackend)

    def test_generate_cache_key(self):
        """Test cache key generation."""
        cache = CacheService()

        # Test basic key generation
        key1 = cache._generate_cache_key("test", param1="value1", param2="value2")
        key2 = cache._generate_cache_key("test", param1="value1", param2="value2")
        assert key1 == key2  # Same parameters should generate same key

        # Test different parameters generate different keys
        key3 = cache._generate_cache_key("test", param1="different", param2="value2")
        assert key1 != key3

        # Test namespace affects key
        key4 = cache._generate_cache_key("different", param1="value1", param2="value2")
        assert key1 != key4

    def test_generate_cache_key_with_datetime(self):
        """Test cache key generation with datetime objects."""
        cache = CacheService()

        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        key = cache._generate_cache_key("test", timestamp=dt)

        # Key should contain ISO format timestamp
        assert key.startswith("birdnet_analytics:")

    def test_generate_cache_key_with_complex_objects(self):
        """Test cache key generation with lists and dicts."""
        cache = CacheService()

        key1 = cache._generate_cache_key("test", data={"a": 1, "b": 2})
        key2 = cache._generate_cache_key("test", data={"b": 2, "a": 1})  # Different order
        assert key1 == key2  # Should be same due to sorted JSON

        key3 = cache._generate_cache_key("test", data=[1, 2, 3])
        assert key1 != key3

    def test_set_and_get_operations(self):
        """Test basic cache set and get operations."""
        cache = CacheService()

        # Test successful set and get
        assert cache.set("test_namespace", "test_value", param="test") is True
        result = cache.get("test_namespace", param="test")
        assert result == "test_value"

        # Test cache miss
        result = cache.get("test_namespace", param="different")
        assert result is None

    def test_delete_operation(self):
        """Test cache delete operation."""
        cache = CacheService()

        # Set then delete
        cache.set("test_namespace", "test_value", param="test")
        assert cache.get("test_namespace", param="test") == "test_value"

        assert cache.delete("test_namespace", param="test") is True
        assert cache.get("test_namespace", param="test") is None

    def test_exists_operation(self):
        """Test cache exists operation."""
        cache = CacheService()

        # Check non-existent
        assert cache.exists("test_namespace", param="test") is False

        # Set and check
        cache.set("test_namespace", "test_value", param="test")
        assert cache.exists("test_namespace", param="test") is True

    def test_clear_operation(self):
        """Test cache clear operation."""
        cache = CacheService()

        # Set multiple items
        cache.set("ns1", "value1", param="test1")
        cache.set("ns2", "value2", param="test2")

        # Clear and verify
        assert cache.clear() is True
        assert cache.get("ns1", param="test1") is None
        assert cache.get("ns2", param="test2") is None

    def test_invalidate_pattern(self):
        """Test cache pattern invalidation."""
        cache = CacheService()

        # Set multiple items
        cache.set("species_summary", "value1", param="test1")
        cache.set("weekly_report", "value2", param="test2")

        # Invalidate pattern (currently clears all)
        assert cache.invalidate_pattern("species_*") is True
        assert cache.get("species_summary", param="test1") is None
        assert cache.get("weekly_report", param="test2") is None

    def test_stats_tracking(self):
        """Test cache statistics tracking."""
        cache = CacheService()

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0

        # Perform operations and check stats
        cache.set("test", "value", param="test")
        stats = cache.get_stats()
        assert stats["sets"] == 1

        # Cache hit
        cache.get("test", param="test")
        stats = cache.get_stats()
        assert stats["hits"] == 1

        # Cache miss
        cache.get("test", param="different")
        stats = cache.get_stats()
        assert stats["misses"] == 1

        # Check hit rate calculation
        assert stats["hit_rate_percent"] == 50.0

    def test_cache_warming(self):
        """Test cache warming functionality."""
        cache = CacheService(enable_cache_warming=True)

        # Define warming functions
        def get_species_summary(**kwargs):
            return {"species": kwargs.get("species", "default"), "count": 100}

        def get_weekly_data(**kwargs):
            return {"week": kwargs.get("week", 1), "total": 50}

        warming_functions = [
            ("species_summary", get_species_summary, {"species": "robin"}, 600),
            ("weekly_report", get_weekly_data, {"week": 1}, 600),
        ]

        # Warm cache
        results = cache.warm_cache(warming_functions)

        # Check results
        assert len(results) == 2
        assert results["species_summary"] is True
        assert results["weekly_report"] is True

        # Verify cached data
        species_data = cache.get("species_summary", species="robin")
        assert species_data == {"species": "robin", "count": 100}

        weekly_data = cache.get("weekly_report", week=1)
        assert weekly_data == {"week": 1, "total": 50}

    def test_cache_warming_disabled(self):
        """Test cache warming when disabled."""
        cache = CacheService(enable_cache_warming=False)

        def dummy_func(**kwargs):
            return "result"

        warming_functions = [("test", dummy_func, {}, 300)]
        results = cache.warm_cache(warming_functions)

        assert results == {}

    def test_cache_warming_already_cached(self):
        """Test cache warming when data is already cached."""
        cache = CacheService(enable_cache_warming=True)

        # Pre-populate cache
        cache.set("test_namespace", "existing_value", param="test")

        def get_new_value(**kwargs):
            return "new_value"

        warming_functions = [("test_namespace", get_new_value, {"param": "test"}, 300)]
        results = cache.warm_cache(warming_functions)

        # Should not overwrite existing data
        assert results["test_namespace"] is True
        assert cache.get("test_namespace", param="test") == "existing_value"

    def test_cache_warming_error_handling(self):
        """Test cache warming error handling."""
        cache = CacheService(enable_cache_warming=True)

        def failing_func(**kwargs):
            raise Exception("Function error")

        warming_functions = [("test", failing_func, {}, 300)]
        results = cache.warm_cache(warming_functions)

        assert results["test"] is False

    def test_health_check_healthy(self):
        """Test health check when cache is healthy."""
        cache = CacheService()

        health = cache.health_check()

        assert health["status"] == "healthy"
        assert health["backend"] == cache.backend_type
        assert "stats" in health

    def test_health_check_unhealthy(self):
        """Test health check when cache is unhealthy."""
        cache = CacheService()

        # Mock backend to fail operations
        with patch.object(cache._backend, "set", return_value=False):
            health = cache.health_check()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Set operation failed"

    def test_ttl_parameter(self):
        """Test custom TTL parameter."""
        cache = CacheService(default_ttl=100)

        # Use default TTL
        cache.set("test", "value1", param="test1")

        # Use custom TTL
        cache.set("test", "value2", ttl=200, param="test2")

        # Both should work normally (can't easily test TTL without waiting)
        assert cache.get("test", param="test1") == "value1"
        assert cache.get("test", param="test2") == "value2"

    def test_error_handling_in_operations(self):
        """Test error handling in cache operations."""
        cache = CacheService()

        # Mock backend to raise errors
        with patch.object(cache._backend, "get", side_effect=Exception("Get error")):
            result = cache.get("test", param="test")
            assert result is None

            stats = cache.get_stats()
            assert stats["errors"] > 0

    def test_complex_data_types(self):
        """Test caching complex data types."""
        cache = CacheService()

        # Test various data types
        complex_data = {
            "list": [1, 2, 3],
            "nested_dict": {"a": {"b": "c"}},
            "datetime": "2025-01-01T12:00:00Z",  # Would normally be datetime
            "null_value": None,
            "boolean": True,
            "number": 42.5,
        }

        cache.set("complex_test", complex_data, param="test")
        result = cache.get("complex_test", param="test")

        assert result == complex_data


class TestCreateCacheService:
    """Test the cache service factory function."""

    def test_create_cache_service_defaults(self):
        """Test factory function with default parameters."""
        cache = create_cache_service()

        assert cache.default_ttl == 300
        assert cache.enable_cache_warming is True

    def test_create_cache_service_custom(self):
        """Test factory function with custom parameters."""
        cache = create_cache_service(
            memcached_host="custom-host",
            memcached_port=11212,
            default_ttl=600,
            enable_cache_warming=False,
        )

        assert cache.default_ttl == 600
        assert cache.enable_cache_warming is False


@pytest.fixture
def sample_cache_service():
    """Fixture providing a cache service for testing."""
    return CacheService(default_ttl=60, enable_cache_warming=True)


class TestIntegrationScenarios:
    """Integration tests for realistic caching scenarios."""

    def test_species_summary_caching(self, sample_cache_service):
        """Test caching species summary data."""
        cache = sample_cache_service

        # Simulate species summary data
        species_data = [
            {"scientific_name": "Turdus migratorius", "count": 15, "avg_confidence": 0.85},
            {"scientific_name": "Corvus brachyrhynchos", "count": 8, "avg_confidence": 0.92},
        ]

        # Cache the data
        cache.set("species_summary", species_data, language_code="en", since="2025-01-01")

        # Retrieve and verify
        cached_data = cache.get("species_summary", language_code="en", since="2025-01-01")
        assert cached_data == species_data

        # Different parameters should miss
        missed_data = cache.get("species_summary", language_code="es", since="2025-01-01")
        assert missed_data is None

    def test_weekly_report_caching(self, sample_cache_service):
        """Test caching weekly report data."""
        cache = sample_cache_service

        # Simulate weekly report data
        weekly_data = {
            "start_date": "2025-01-06",
            "end_date": "2025-01-12",
            "total_detections": 150,
            "unique_species": 25,
            "top_species": ["Robin", "Crow", "Sparrow"],
        }

        # Cache with specific week parameters
        cache.set("weekly_report", weekly_data, week=2, year=2025)

        # Retrieve and verify
        cached_data = cache.get("weekly_report", week=2, year=2025)
        assert cached_data == weekly_data

    def test_cache_invalidation_scenario(self, sample_cache_service):
        """Test cache invalidation when new data is added."""
        cache = sample_cache_service

        # Cache some data
        cache.set("today_detections", ["detection1", "detection2"], date="2025-01-01")

        # Simulate new detection added - invalidate cache
        cache.delete("today_detections", date="2025-01-01")

        # Should be cache miss now
        result = cache.get("today_detections", date="2025-01-01")
        assert result is None

    def test_performance_monitoring(self, sample_cache_service):
        """Test performance monitoring with realistic usage."""
        cache = sample_cache_service

        # Simulate realistic cache usage patterns
        for i in range(10):
            cache.set(f"detection_{i}", f"data_{i}", detection_id=i)

        # Mix of hits and misses
        for i in range(15):  # 10 hits, 5 misses
            cache.get(f"detection_{i}", detection_id=i)

        stats = cache.get_stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["sets"] == 10
        assert stats["hit_rate_percent"] == 66.67
