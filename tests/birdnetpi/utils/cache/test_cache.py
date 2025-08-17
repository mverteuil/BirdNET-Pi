"""Tests for cache decorator."""

from unittest.mock import MagicMock, patch

from birdnetpi.utils.cache import (
    cached,
    cached_function,
    clear_all_cache,
    invalidate_cache,
)
from birdnetpi.utils.cache.decorator import _generate_cache_key


class TestCacheDecorator:
    """Test the @cached decorator for methods."""

    def test_cached_method_caches_result(self):
        """Should cache method results and return cached value on subsequent calls."""

        class TestClass:
            def __init__(self):
                self.call_count = 0

            @cached(ttl=300, key_prefix="test")
            def expensive_method(self, x, y):
                self.call_count += 1
                return x + y

        with patch("birdnetpi.utils.cache.decorator.Cache") as mock_cache:
            mock_backend = MagicMock()
            mock_cache.return_value._backend = mock_backend

            # First call - cache miss
            mock_backend.get.return_value = None
            mock_backend.set.return_value = True

            obj = TestClass()
            result1 = obj.expensive_method(2, 3)

            assert result1 == 5
            assert obj.call_count == 1
            mock_backend.get.assert_called_once()
            mock_backend.set.assert_called_once()

            # Second call - cache hit
            mock_backend.get.return_value = 5
            result2 = obj.expensive_method(2, 3)

            assert result2 == 5
            assert obj.call_count == 1  # Method not called again

    def test_cached_with_different_args_generates_different_keys(self):
        """Should generate different cache keys for different arguments."""

        class TestClass:
            @cached(ttl=300)
            def method(self, x):
                return x * 2

        with patch("birdnetpi.utils.cache.decorator.Cache") as mock_cache:
            mock_backend = MagicMock()
            mock_cache.return_value._backend = mock_backend
            mock_backend.get.return_value = None

            obj = TestClass()

            # Track the cache keys used
            set_calls = []
            mock_backend.set.side_effect = lambda key, val, ttl: set_calls.append(key) or True

            obj.method(1)
            obj.method(2)

            # Different arguments should generate different keys
            assert len(set_calls) == 2
            assert set_calls[0] != set_calls[1]


class TestCachedFunction:
    """Test the @cached_function decorator for standalone functions."""

    def test_cached_function_caches_result(self):
        """Should cache function results and return cached value on subsequent calls."""
        call_count = 0

        @cached_function(ttl=600, key_prefix="standalone")
        def expensive_function(x, y):
            nonlocal call_count
            call_count += 1
            return x * y

        with patch("birdnetpi.utils.cache.decorator.Cache") as mock_cache:
            mock_backend = MagicMock()
            mock_cache.return_value._backend = mock_backend

            # First call - cache miss
            mock_backend.get.return_value = None
            result1 = expensive_function(3, 4)

            assert result1 == 12
            assert call_count == 1

            # Second call - cache hit
            mock_backend.get.return_value = 12
            result2 = expensive_function(3, 4)

            assert result2 == 12
            assert call_count == 1  # Function not called again


class TestGenerateCacheKey:
    """Test cache key generation."""

    def test_generate_cache_key_basic(self):
        """Should generate consistent cache keys for same arguments."""
        key1 = _generate_cache_key("test_func", (1, 2), {"a": 3}, "prefix")
        key2 = _generate_cache_key("test_func", (1, 2), {"a": 3}, "prefix")

        assert key1 == key2
        assert len(key1) == 32  # MD5 hash length

    def test_generate_cache_key_different_args(self):
        """Should generate different keys for different arguments."""
        key1 = _generate_cache_key("test_func", (1, 2), {"a": 3}, "prefix")
        key2 = _generate_cache_key("test_func", (1, 3), {"a": 3}, "prefix")
        key3 = _generate_cache_key("test_func", (1, 2), {"a": 4}, "prefix")

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_generate_cache_key_with_complex_types(self):
        """Should handle complex types in arguments."""
        # Test with lists
        key1 = _generate_cache_key("func", ([1, 2, 3],), {}, None)
        key2 = _generate_cache_key("func", ([1, 2, 3],), {}, None)
        assert key1 == key2

        # Test with dicts
        key3 = _generate_cache_key("func", (), {"data": {"x": 1, "y": 2}}, None)
        key4 = _generate_cache_key("func", (), {"data": {"y": 2, "x": 1}}, None)
        assert key3 == key4  # Order shouldn't matter for dicts

    def test_generate_cache_key_with_objects(self):
        """Should handle objects with __dict__ attribute."""

        class TestObj:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        obj1 = TestObj(1, 2)
        obj2 = TestObj(1, 2)

        key1 = _generate_cache_key("func", (obj1,), {}, None)
        key2 = _generate_cache_key("func", (obj2,), {}, None)

        assert key1 == key2  # Same object state should generate same key


class TestCacheInvalidation:
    """Test cache invalidation functions."""

    def test_invalidate_cache(self):
        """Should invalidate specific cache entries."""
        with patch("birdnetpi.utils.cache.decorator.Cache") as mock_cache:
            mock_instance = MagicMock()
            mock_cache.return_value = mock_instance
            mock_instance.delete.return_value = True

            result = invalidate_cache("test_namespace", key1="value1")

            assert result is True
            mock_instance.delete.assert_called_once_with("test_namespace", key1="value1")

    def test_clear_all_cache(self):
        """Should clear all cached data."""
        with patch("birdnetpi.utils.cache.decorator.Cache") as mock_cache:
            mock_instance = MagicMock()
            mock_cache.return_value = mock_instance
            mock_instance.clear.return_value = True

            result = clear_all_cache()

            assert result is True
            mock_instance.clear.assert_called_once()
