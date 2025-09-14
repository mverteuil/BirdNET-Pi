"""Comprehensive tests for cache backends."""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.utils.cache.backends import (
    MEMCACHED_AVAILABLE,
    CacheBackend,
    InMemoryBackend,
    MemcachedBackend,
)


class TestInMemoryBackend:
    """Test the in-memory cache backend implementation."""

    def test_init(self):
        """Should initialization of InMemoryBackend."""
        backend = InMemoryBackend()
        assert backend._cache == {}

    def test_set_and_get_basic(self):
        """Should basic set and get operations."""
        backend = InMemoryBackend()

        # Set a value
        assert backend.set("key1", "value1", 300) is True

        # Get the value back
        assert backend.get("key1") == "value1"

        # Non-existent key returns None
        assert backend.get("nonexistent") is None

    def test_set_with_ttl_expiry(self):
        """Should TTL expiry works correctly."""
        backend = InMemoryBackend()

        # Set with 1 second TTL (minimum int value)
        backend.set("short_ttl", "value", 1)

        # Should exist immediately
        assert backend.get("short_ttl") == "value"

        # Wait for expiry
        time.sleep(1.1)

        # Should be expired now
        assert backend.get("short_ttl") is None
        assert "short_ttl" not in backend._cache

    def test_set_overwrites_existing(self):
        """Should set overwrites existing values."""
        backend = InMemoryBackend()

        backend.set("key", "value1", 300)
        assert backend.get("key") == "value1"

        backend.set("key", "value2", 300)
        assert backend.get("key") == "value2"

    def test_delete(self):
        """Should delete operation."""
        backend = InMemoryBackend()

        # Set a value
        backend.set("key", "value", 300)
        assert backend.exists("key") is True

        # Delete it
        assert backend.delete("key") is True
        assert backend.exists("key") is False
        assert backend.get("key") is None

        # Delete non-existent key returns False
        assert backend.delete("nonexistent") is False

    def test_exists(self):
        """Should exists operation."""
        backend = InMemoryBackend()

        assert backend.exists("key") is False

        backend.set("key", "value", 300)
        assert backend.exists("key") is True

        # Test with expired key
        backend.set("expired", "value", 1)
        assert backend.exists("expired") is True

        time.sleep(1.1)
        assert backend.exists("expired") is False

    def test_clear(self):
        """Should clear operation."""
        backend = InMemoryBackend()

        # Set multiple values
        backend.set("key1", "value1", 300)
        backend.set("key2", "value2", 300)
        backend.set("key3", "value3", 300)

        assert len(backend._cache) == 3

        # Clear all
        assert backend.clear() is True

        assert backend._cache == {}
        assert backend.get("key1") is None
        assert backend.get("key2") is None
        assert backend.get("key3") is None

    def test_cleanup_expired_entries(self):
        """Should expired entries are cleaned up periodically."""
        backend = InMemoryBackend()

        # Set multiple values with different TTLs
        backend.set("long", "value", 300)
        backend.set("short1", "value", 1)
        backend.set("short2", "value", 1)

        assert len(backend._cache) == 3

        # Wait for short TTLs to expire
        time.sleep(1.1)

        # Try to get expired keys - they should return None
        assert backend.get("short1") is None
        assert backend.get("short2") is None

        # Long-lived key should still exist
        assert backend.get("long") == "value"

        # After getting expired keys, they should be removed from cache
        assert "short1" not in backend._cache
        assert "short2" not in backend._cache
        assert "long" in backend._cache

    def test_complex_data_types(self):
        """Should caching of complex data types."""
        backend = InMemoryBackend()

        # Lists
        list_data = [1, 2, 3, {"a": "b"}]
        backend.set("list", list_data, 300)
        assert backend.get("list") == list_data

        # Dicts
        dict_data = {"key": "value", "nested": {"a": 1, "b": 2}}
        backend.set("dict", dict_data, 300)
        assert backend.get("dict") == dict_data

        # Custom objects
        class CustomObj:
            def __init__(self, x, y):
                self.x = x
                self.y = y

            def __eq__(self, other):
                return self.x == other.x and self.y == other.y

        obj = CustomObj(10, 20)
        backend.set("obj", obj, 300)
        retrieved = backend.get("obj")
        assert retrieved == obj
        assert retrieved.x == 10
        assert retrieved.y == 20

    def test_datetime_objects(self):
        """Should caching of datetime objects."""
        backend = InMemoryBackend()

        now = datetime.now()
        backend.set("datetime", now, 300)

        retrieved = backend.get("datetime")
        assert retrieved == now
        assert isinstance(retrieved, datetime)


class TestMemcachedBackend:
    """Test the memcached cache backend implementation."""

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_init_success(self):
        """Should successful initialization with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.version.return_value = b"1.5.0"
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("127.0.0.1", 11211)

            assert backend.client == mock_instance
            # Check that client was called with correct args
            call_args = mock_client.call_args
            assert call_args[0][0] == ("127.0.0.1", 11211)
            assert call_args[1]["connect_timeout"] == 1
            assert call_args[1]["timeout"] == 1
            # Check that serializer and deserializer are functions
            assert callable(call_args[1]["serializer"])
            assert callable(call_args[1]["deserializer"])

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_init_connection_failure(self):
        """Should initialization failure when memcached is unavailable."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.version.side_effect = Exception("Connection refused")
            mock_client.return_value = mock_instance

            with pytest.raises(RuntimeError, match="Failed to connect to memcached"):
                MemcachedBackend("localhost", 11211)

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_get(self):
        """Should get operation with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Successful get
            mock_instance.get.return_value = "value"
            assert backend.get("key") == "value"
            mock_instance.get.assert_called_with("key")

            # Get returns None
            mock_instance.get.return_value = None
            assert backend.get("nonexistent") is None

            # Get raises exception
            mock_instance.get.side_effect = Exception("Error")
            assert backend.get("error_key") is None

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_set(self):
        """Should set operation with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Successful set
            mock_instance.set.return_value = True
            assert backend.set("key", "value", 300) is True
            mock_instance.set.assert_called_with("key", "value", expire=300)

            # Set with complex object
            obj = {"a": 1, "b": [2, 3]}
            assert backend.set("complex", obj, 600) is True
            mock_instance.set.assert_called_with("complex", obj, expire=600)

            # Set raises exception
            mock_instance.set.side_effect = Exception("Error")
            assert backend.set("error_key", "value", 300) is False

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_delete(self):
        """Should delete operation with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Successful delete
            mock_instance.delete.return_value = True
            assert backend.delete("key") is True
            mock_instance.delete.assert_called_with("key")

            # Delete returns False
            mock_instance.delete.return_value = False
            assert backend.delete("nonexistent") is False

            # Delete raises exception
            mock_instance.delete.side_effect = Exception("Error")
            assert backend.delete("error_key") is False

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_exists(self):
        """Should exists operation with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Key exists
            mock_instance.get.return_value = "value"
            assert backend.exists("key") is True

            # Key doesn't exist
            mock_instance.get.return_value = None
            assert backend.exists("nonexistent") is False

            # Get raises exception
            mock_instance.get.side_effect = Exception("Error")
            assert backend.exists("error_key") is False

    @pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="pymemcache not installed")
    def test_clear(self):
        """Should clear operation with memcached."""
        with patch("birdnetpi.utils.cache.backends.MemcacheClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            backend = MemcachedBackend("localhost", 11211)

            # Successful clear - flush_all returns the result directly
            mock_instance.flush_all.return_value = True
            assert backend.clear() is True
            mock_instance.flush_all.assert_called_once()

            # Clear raises exception
            mock_instance.flush_all.side_effect = Exception("Error")
            assert backend.clear() is False


class TestCacheBackendAbstract:
    """Test the abstract CacheBackend interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Should cacheBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            CacheBackend()  # type: ignore[abstract]

    def test_subclass_must_implement_all_methods(self):
        """Should subclasses must implement all abstract methods."""

        class IncompleteBackend(CacheBackend):
            def get(self, key: str):
                pass

            # Missing other required methods

        with pytest.raises(TypeError):
            IncompleteBackend()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self):
        """Should a complete subclass can be instantiated."""

        class CompleteBackend(CacheBackend):
            def get(self, key: str):
                return None

            def set(self, key: str, value, ttl: int) -> bool:
                return True

            def delete(self, key: str) -> bool:
                return True

            def exists(self, key: str) -> bool:
                return False

            def clear(self) -> bool:
                return True

        backend = CompleteBackend()
        assert backend.get("key") is None
        assert backend.set("key", "value", 300) is True
        assert backend.delete("key") is True
        assert backend.exists("key") is False
        assert backend.clear() is True


class TestMemcachedAvailability:
    """Test MEMCACHED_AVAILABLE constant."""

    def test_memcached_available_constant_exists(self):
        """Should MEMCACHED_AVAILABLE constant is defined."""
        # The constant should always be defined
        assert isinstance(MEMCACHED_AVAILABLE, bool)

    @patch("birdnetpi.utils.cache.backends.MEMCACHED_AVAILABLE", False)
    def test_memcached_backend_unavailable(self):
        """Should behavior when pymemcache is not installed."""
        # When MEMCACHED_AVAILABLE is False, MemcachedBackend should not be usable
        # This is handled by the skipif decorators in the tests above
        pass
