"""Cache decorator for method results.

This module provides a decorator for caching expensive method results using
the CacheService. It's particularly useful for analytics queries, database
operations, and any other computationally expensive operations.
"""

import hashlib
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from birdnetpi.utils.cache.cache import Cache


def cached(ttl: int = 300, key_prefix: str | None = None) -> Callable:
    """Cache method results to avoid redundant computations.

    This decorator caches the results of method calls, avoiding redundant
    computations for expensive operations. It's particularly useful for:
    - Analytics calculations
    - Database queries
    - API responses
    - Complex data transformations

    Args:
        ttl: Time-to-live in seconds for cached results (default: 300)
        key_prefix: Optional prefix for cache keys to avoid collisions

    Returns:
        Decorated function that caches its results

    Example:
        @cached(ttl=600, key_prefix="species_summary")
        def get_species_summary(self, start_date, end_date):
            # Expensive database query
            return self._calculate_summary(start_date, end_date)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            # Generate cache key from function name and arguments
            cache_key = _generate_cache_key(func.__name__, args, kwargs, key_prefix)

            # Try to get from cache
            cache = Cache()
            cached_value = cache._backend.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = func(self, *args, **kwargs)
            cache._backend.set(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


def cached_function(ttl: int = 300, key_prefix: str | None = None) -> Callable:
    """Cache function results (non-method version).

    Similar to @cached but for standalone functions rather than methods.

    Args:
        ttl: Time-to-live in seconds for cached results (default: 300)
        key_prefix: Optional prefix for cache keys to avoid collisions

    Returns:
        Decorated function that caches its results

    Example:
        @cached_function(ttl=3600, key_prefix="bird_data")
        def fetch_bird_data(species_id):
            # Expensive API call
            return api.get_bird_info(species_id)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            # Generate cache key from function name and arguments
            cache_key = _generate_cache_key(func.__name__, args, kwargs, key_prefix)

            # Try to get from cache
            cache = Cache()
            cached_value = cache._backend.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache._backend.set(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


def _generate_cache_key(
    func_name: str, args: tuple, kwargs: dict, prefix: str | None = None
) -> str:
    """Generate a unique cache key from function arguments.

    Creates a deterministic cache key based on function name and all arguments.
    Uses MD5 hashing to ensure consistent key length regardless of argument complexity.

    Args:
        func_name: Name of the function being cached
        args: Positional arguments passed to the function
        kwargs: Keyword arguments passed to the function
        prefix: Optional prefix to avoid key collisions

    Returns:
        MD5 hash of the cache key components
    """
    key_parts = [prefix or "", func_name]

    # Add positional arguments
    for arg in args:
        if hasattr(arg, "__dict__"):
            # For objects, use their dict representation
            key_parts.append(json.dumps(arg.__dict__, sort_keys=True, default=str))
        elif isinstance(arg, list | dict):
            # For collections, use JSON serialization
            key_parts.append(json.dumps(arg, sort_keys=True, default=str))
        else:
            key_parts.append(str(arg))

    # Add keyword arguments (sorted for consistency)
    for k, v in sorted(kwargs.items()):
        if hasattr(v, "__dict__"):
            key_parts.append(f"{k}={json.dumps(v.__dict__, sort_keys=True, default=str)}")
        elif isinstance(v, list | dict):
            key_parts.append(f"{k}={json.dumps(v, sort_keys=True, default=str)}")
        else:
            key_parts.append(f"{k}={v}")

    # Create key string and hash it
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def invalidate_cache(namespace: str, **kwargs: Any) -> bool:  # noqa: ANN401
    """Invalidate cached entries for a specific namespace.

    This function allows manual cache invalidation when data changes.

    Args:
        namespace: Cache namespace to invalidate
        **kwargs: Additional parameters for cache key generation

    Returns:
        True if successful, False otherwise

    Example:
        # Invalidate all species summary cache entries
        invalidate_cache("species_summary", date="2024-01-01")
    """
    cache = Cache()
    return cache.delete(namespace, **kwargs)


def clear_all_cache() -> bool:
    """Clear all cached data.

    Use with caution as this will remove ALL cached entries.

    Returns:
        True if successful, False otherwise
    """
    cache = Cache()
    return cache.clear()
