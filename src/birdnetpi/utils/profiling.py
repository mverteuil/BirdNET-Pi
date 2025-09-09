"""Performance profiling utilities for BirdNET-Pi."""

import functools
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Simple performance profiler for measuring execution times."""

    def __init__(self, name: str = "Operation"):
        self.name = name
        self.timings: dict[str, list[float]] = {}
        self.current_stack: list[tuple[str, float]] = []

    @contextmanager
    def profile(self, operation: str):
        """Context manager for profiling synchronous operations."""
        start_time = time.perf_counter()
        self.current_stack.append((operation, start_time))
        try:
            yield self
        finally:
            elapsed = time.perf_counter() - start_time
            self.current_stack.pop()

            if operation not in self.timings:
                self.timings[operation] = []
            self.timings[operation].append(elapsed)

            # Log if operation took more than 100ms
            if elapsed > 0.1:
                logger.warning("%s: %s took %.3f seconds", self.name, operation, elapsed)

    @asynccontextmanager
    async def aprofile(self, operation: str):
        """Context manager for profiling async operations."""
        start_time = time.perf_counter()
        self.current_stack.append((operation, start_time))
        try:
            yield self
        finally:
            elapsed = time.perf_counter() - start_time
            self.current_stack.pop()

            if operation not in self.timings:
                self.timings[operation] = []
            self.timings[operation].append(elapsed)

            # Log if operation took more than 100ms
            if elapsed > 0.1:
                logger.warning("%s: %s took %.3f seconds", self.name, operation, elapsed)

    def get_report(self) -> dict[str, Any]:
        """Generate a performance report."""
        report = {
            "name": self.name,
            "operations": {},
            "total_time": 0.0,
        }

        for operation, times in self.timings.items():
            total = sum(times)
            report["operations"][operation] = {
                "count": len(times),
                "total": round(total, 3),
                "average": round(total / len(times), 3) if times else 0,
                "min": round(min(times), 3) if times else 0,
                "max": round(max(times), 3) if times else 0,
            }
            report["total_time"] += total

        report["total_time"] = round(report["total_time"], 3)
        return report

    def log_report(self):
        """Log the performance report."""
        report = self.get_report()
        logger.info(
            "Performance Report for %s (Total: %.3fs)", report["name"], report["total_time"]
        )

        # Sort by total time descending
        sorted_ops = sorted(report["operations"].items(), key=lambda x: x[1]["total"], reverse=True)

        for operation, stats in sorted_ops:
            logger.info(
                "  %s: %.3fs (count=%d, avg=%.3fs, min=%.3fs, max=%.3fs)",
                operation,
                stats["total"],
                stats["count"],
                stats["average"],
                stats["min"],
                stats["max"],
            )


def profile_async(name: str | None = None):
    """Decorator for profiling async functions."""

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            operation_name = name or f"{func.__module__}.{func.__name__}"
            profiler = PerformanceProfiler(operation_name)

            async with profiler.aprofile("total"):
                result = await func(*args, **kwargs, _profiler=profiler)

            profiler.log_report()
            return result

        return wrapper

    return decorator


def profile_sync(name: str | None = None):
    """Decorator for profiling synchronous functions."""

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            operation_name = name or f"{func.__module__}.{func.__name__}"
            profiler = PerformanceProfiler(operation_name)

            with profiler.profile("total"):
                result = func(*args, **kwargs, _profiler=profiler)

            profiler.log_report()
            return result

        return wrapper

    return decorator


class RequestProfiler:
    """Middleware for profiling HTTP requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]

        start_time = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                elapsed = time.perf_counter() - start_time
                if elapsed > 0.5:  # Log slow requests (>500ms)
                    logger.warning("Slow request: %s %s took %.3f seconds", method, path, elapsed)
                # Add timing header
                message.setdefault("headers", []).append(
                    (b"x-response-time", f"{elapsed:.3f}s".encode())
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
