"""Cache utilities for BirdNET-Pi.

This package provides caching functionality for expensive operations like
analytics queries, database operations, and API responses.

Main components:
- Cache: Main cache class with Redis backend
- Decorators: @cached and @cached_function for easy caching
- Backend: RedisBackend implementation for memory-only caching
"""

# Import backend classes
from birdnetpi.utils.cache.backends import CacheBackend, RedisBackend

# Import main cache class
from birdnetpi.utils.cache.cache import Cache

# Import decorators and utilities
from birdnetpi.utils.cache.decorator import (
    cached,
    cached_function,
    clear_all_cache,
    invalidate_cache,
)

__all__ = [
    "Cache",
    "CacheBackend",
    "RedisBackend",
    "cached",
    "cached_function",
    "clear_all_cache",
    "invalidate_cache",
]
