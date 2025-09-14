"""Core tests for Cache class initialization and factory functions.

This module tests the Cache class's backend selection logic and initialization.
The actual cache operations are tested in:
- test_cache_with_memory.py (InMemoryBackend tests)
- test_cache_with_memcached.py (MemcachedBackend tests)
"""

from unittest.mock import MagicMock, patch

from birdnetpi.utils.cache.cache import Cache, create_cache


class TestCacheInitialization:
    """Test Cache class initialization with different backends."""

    @patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", True)
    @patch("birdnetpi.utils.cache.cache.MemcachedBackend")
    def test_init_with_memcached_success(self, mock_memcached_backend):
        """Should successful initialization with memcached backend."""
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
        """Should fallback to in-memory backend when memcached fails."""
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
        """Should initialization when memcached is not available."""
        mock_memory = MagicMock()
        mock_memory_backend.return_value = mock_memory

        cache = Cache()

        assert cache.backend_type == "memory"
        assert cache._backend == mock_memory
        assert cache.default_ttl == 300
        assert cache.enable_cache_warming is True

    @patch("birdnetpi.utils.cache.cache.InMemoryBackend")
    def test_init_statistics_tracking(self, mock_memory_backend):
        """Should statistics are initialized correctly."""
        with patch("birdnetpi.utils.cache.cache.MEMCACHED_AVAILABLE", False):
            cache = Cache()

            assert cache._stats == {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0,
            }


class TestCreateCache:
    """Test the create_cache factory function."""

    def test_create_cache_default(self):
        """Should create_cache with default parameters."""
        with patch("birdnetpi.utils.cache.cache.Cache") as mock_cache:
            create_cache()

            mock_cache.assert_called_once_with(
                memcached_host="localhost",
                memcached_port=11211,
                default_ttl=300,
                enable_cache_warming=True,
            )

    def test_create_cache_custom(self):
        """Should create_cache with custom parameters."""
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
