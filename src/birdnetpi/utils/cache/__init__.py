"""Cache utilities for BirdNET-Pi.

This package provides caching functionality for expensive operations like
analytics queries, database operations, and API responses.

Main components:
- Cache: Main cache class with automatic backend selection
- CacheService: Backward compatibility alias for Cache
- Decorators: @cached and @cached_function for easy caching
- Backends: MemcachedBackend and InMemoryBackend implementations
"""

# Import backend classes
from birdnetpi.utils.cache.backends import (
    MEMCACHED_AVAILABLE,
    CacheBackend,
    InMemoryBackend,
    MemcachedBackend,
)

# Import main cache class and factory
from birdnetpi.utils.cache.cache import Cache, create_cache

# Import decorators and utilities
from birdnetpi.utils.cache.decorator import (
    cached,
    cached_function,
    clear_all_cache,
    invalidate_cache,
)

__all__ = [
    "MEMCACHED_AVAILABLE",
    "Cache",
    "CacheBackend",
    "InMemoryBackend",
    "MemcachedBackend",
    "cached",
    "cached_function",
    "clear_all_cache",
    "create_cache",
    "invalidate_cache",
]
