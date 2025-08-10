"""Query performance monitoring for analytics operations.

This module provides real-time monitoring of database query performance,
helping identify slow queries and optimization opportunities.
"""

import functools
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class QueryMonitor:
    """Monitor and track database query performance."""

    def __init__(self, max_history: int = 1000, slow_query_threshold_ms: float = 100.0):
        """Initialize the query monitor.

        Args:
            max_history: Maximum number of queries to keep in history
            slow_query_threshold_ms: Threshold in milliseconds to consider a query slow
        """
        self.max_history = max_history
        self.slow_query_threshold_ms = slow_query_threshold_ms

        # Query history (newest first)
        self.query_history: deque = deque(maxlen=max_history)

        # Slow query log
        self.slow_queries: deque = deque(maxlen=100)

        # Query pattern statistics
        self.query_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "total_time_ms": 0,
                "min_time_ms": float("inf"),
                "max_time_ms": 0,
                "avg_time_ms": 0,
                "last_executed": None,
            }
        )

        # Active queries (for tracking currently executing queries)
        self.active_queries: dict[int, dict[str, Any]] = {}

        # Global statistics
        self.global_stats = {
            "total_queries": 0,
            "total_time_ms": 0,
            "slow_query_count": 0,
            "monitoring_started": datetime.now(),
        }

    def start_query(self, query_id: int, query: str, params: dict[str, Any] | None = None) -> None:
        """Record the start of a query execution.

        Args:
            query_id: Unique identifier for this query execution
            query: SQL query string
            params: Query parameters
        """
        self.active_queries[query_id] = {
            "query": query,
            "params": params,
            "start_time": time.perf_counter(),
            "started_at": datetime.now(),
        }

    def end_query(self, query_id: int) -> float | None:
        """Record the end of a query execution.

        Args:
            query_id: Unique identifier for this query execution

        Returns:
            Execution time in milliseconds, or None if query not found
        """
        if query_id not in self.active_queries:
            return None

        query_info = self.active_queries.pop(query_id)
        execution_time_ms = (time.perf_counter() - query_info["start_time"]) * 1000

        # Record in history
        history_entry = {
            "query": query_info["query"],
            "params": query_info["params"],
            "execution_time_ms": execution_time_ms,
            "started_at": query_info["started_at"],
            "completed_at": datetime.now(),
        }
        self.query_history.appendleft(history_entry)

        # Update global statistics
        self.global_stats["total_queries"] += 1
        self.global_stats["total_time_ms"] += execution_time_ms

        # Check if it's a slow query
        if execution_time_ms >= self.slow_query_threshold_ms:
            self.global_stats["slow_query_count"] += 1
            self.slow_queries.appendleft(history_entry)
            logger.warning(
                f"Slow query detected ({execution_time_ms:.2f}ms): "
                f"{self._truncate_query(query_info['query'])}"
            )

        # Update pattern statistics
        pattern = self._extract_query_pattern(query_info["query"])
        stats = self.query_stats[pattern]
        stats["count"] += 1
        stats["total_time_ms"] += execution_time_ms
        stats["min_time_ms"] = min(stats["min_time_ms"], execution_time_ms)
        stats["max_time_ms"] = max(stats["max_time_ms"], execution_time_ms)
        stats["avg_time_ms"] = stats["total_time_ms"] / stats["count"]
        stats["last_executed"] = datetime.now()

        return execution_time_ms

    def _extract_query_pattern(self, query: str) -> str:
        """Extract a normalized pattern from a query for grouping statistics.

        Args:
            query: SQL query string

        Returns:
            Normalized query pattern
        """
        # Remove extra whitespace and convert to uppercase
        pattern = " ".join(query.split()).upper()

        # Remove specific values to generalize the pattern
        # This is a simple implementation; could be enhanced with proper SQL parsing
        import re

        # Replace quoted strings
        pattern = re.sub(r"'[^']*'", "'?'", pattern)
        pattern = re.sub(r'"[^"]*"', '"?"', pattern)

        # Replace numbers
        pattern = re.sub(r"\b\d+\b", "?", pattern)

        # Replace parameter placeholders
        pattern = re.sub(r":\w+", ":param", pattern)

        # Truncate very long patterns
        if len(pattern) > 200:
            pattern = pattern[:200] + "..."

        return pattern

    def _truncate_query(self, query: str, max_length: int = 100) -> str:
        """Truncate a query string for display.

        Args:
            query: SQL query string
            max_length: Maximum length for display

        Returns:
            Truncated query string
        """
        query = " ".join(query.split())  # Normalize whitespace
        if len(query) <= max_length:
            return query
        return query[: max_length - 3] + "..."

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive query statistics.

        Returns:
            Dictionary containing various statistics
        """
        uptime_seconds = (datetime.now() - self.global_stats["monitoring_started"]).total_seconds()

        stats = {
            "global": {
                "total_queries": self.global_stats["total_queries"],
                "total_time_ms": round(self.global_stats["total_time_ms"], 2),
                "slow_query_count": self.global_stats["slow_query_count"],
                "slow_query_percentage": (
                    round(
                        self.global_stats["slow_query_count"]
                        / max(self.global_stats["total_queries"], 1)
                        * 100,
                        2,
                    )
                ),
                "average_time_ms": (
                    round(
                        self.global_stats["total_time_ms"]
                        / max(self.global_stats["total_queries"], 1),
                        2,
                    )
                ),
                "queries_per_second": (
                    round(self.global_stats["total_queries"] / max(uptime_seconds, 1), 2)
                ),
                "monitoring_started": self.global_stats["monitoring_started"].isoformat(),
                "uptime_seconds": round(uptime_seconds, 2),
            },
            "active_queries": len(self.active_queries),
            "history_size": len(self.query_history),
            "slow_queries_logged": len(self.slow_queries),
        }

        # Add top slow queries
        if self.slow_queries:
            stats["recent_slow_queries"] = [
                {
                    "query": self._truncate_query(q["query"]),
                    "execution_time_ms": round(q["execution_time_ms"], 2),
                    "started_at": q["started_at"].isoformat(),
                }
                for q in list(self.slow_queries)[:5]
            ]

        # Add query pattern statistics (top 10 by count)
        if self.query_stats:
            sorted_patterns = sorted(
                self.query_stats.items(), key=lambda x: x[1]["count"], reverse=True
            )[:10]

            stats["top_query_patterns"] = [
                {
                    "pattern": self._truncate_query(pattern, 150),
                    "count": stats["count"],
                    "avg_time_ms": round(stats["avg_time_ms"], 2),
                    "min_time_ms": round(stats["min_time_ms"], 2),
                    "max_time_ms": round(stats["max_time_ms"], 2),
                    "total_time_ms": round(stats["total_time_ms"], 2),
                    "last_executed": stats["last_executed"].isoformat()
                    if stats["last_executed"]
                    else None,
                }
                for pattern, stats in sorted_patterns
            ]

        return stats

    def get_slow_query_report(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get a detailed report of slow queries.

        Args:
            limit: Maximum number of slow queries to return

        Returns:
            List of slow query details
        """
        return [
            {
                "query": q["query"],
                "execution_time_ms": round(q["execution_time_ms"], 2),
                "params": q.get("params"),
                "started_at": q["started_at"].isoformat(),
                "completed_at": q["completed_at"].isoformat(),
            }
            for q in list(self.slow_queries)[:limit]
        ]

    def clear_history(self) -> None:
        """Clear query history and statistics."""
        self.query_history.clear()
        self.slow_queries.clear()
        self.query_stats.clear()
        self.active_queries.clear()

        # Reset global stats but keep monitoring start time
        self.global_stats = {
            "total_queries": 0,
            "total_time_ms": 0,
            "slow_query_count": 0,
            "monitoring_started": self.global_stats["monitoring_started"],
        }


def monitor_queries(monitor: QueryMonitor) -> Callable:
    """Decorator to monitor query execution time.

    Args:
        monitor: QueryMonitor instance

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract query from arguments
            query = None
            if args and isinstance(args[0], str):
                query = args[0]
            elif "query" in kwargs:
                query = kwargs["query"]

            if query:
                query_id = id(query) + int(time.time() * 1000000)
                monitor.start_query(query_id, query, kwargs.get("params"))

                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    monitor.end_query(query_id)
            else:
                # If we can't extract the query, just execute normally
                return func(*args, **kwargs)

        return wrapper

    return decorator


def setup_sqlalchemy_monitoring(engine: Engine, monitor: QueryMonitor) -> None:
    """Set up SQLAlchemy event listeners for query monitoring.

    Args:
        engine: SQLAlchemy engine
        monitor: QueryMonitor instance
    """

    @event.listens_for(engine, "before_execute")
    def before_execute(conn, clauseelement, multiparams, params, execution_options):
        """Record query start."""
        query_id = id(clauseelement)
        query_text = str(clauseelement)
        monitor.start_query(query_id, query_text, params)
        conn.info["query_start_time"] = time.perf_counter()
        conn.info["query_id"] = query_id

    @event.listens_for(engine, "after_execute")
    def after_execute(conn, clauseelement, multiparams, params, execution_options, result):
        """Record query completion."""
        query_id = conn.info.get("query_id")
        if query_id:
            monitor.end_query(query_id)
            conn.info.pop("query_start_time", None)
            conn.info.pop("query_id", None)


class QueryOptimizationRecommender:
    """Generate query optimization recommendations based on monitoring data."""

    def __init__(self, monitor: QueryMonitor):
        """Initialize the recommender.

        Args:
            monitor: QueryMonitor instance
        """
        self.monitor = monitor

    def generate_recommendations(self) -> list[str]:
        """Generate optimization recommendations based on query statistics.

        Returns:
            List of recommendation strings
        """
        recommendations = []
        stats = self.monitor.get_statistics()

        # Check for high percentage of slow queries
        if stats["global"]["slow_query_percentage"] > 10:
            recommendations.append(
                f"High percentage of slow queries ({stats['global']['slow_query_percentage']}%). "
                "Consider running database optimization or adding indexes."
            )

        # Check for specific slow query patterns
        if "top_query_patterns" in stats:
            for pattern_stat in stats["top_query_patterns"]:
                if pattern_stat["avg_time_ms"] > 100:
                    pattern = pattern_stat["pattern"][:50] + "..."
                    recommendations.append(
                        f"Query pattern '{pattern}' has high average execution time "
                        f"({pattern_stat['avg_time_ms']}ms). Consider optimization."
                    )

        # Check for queries with high variance
        if "top_query_patterns" in stats:
            for pattern_stat in stats["top_query_patterns"]:
                if pattern_stat["max_time_ms"] > pattern_stat["min_time_ms"] * 10:
                    pattern = pattern_stat["pattern"][:50] + "..."
                    min_time = pattern_stat["min_time_ms"]
                    max_time = pattern_stat["max_time_ms"]
                    recommendations.append(
                        f"Query pattern '{pattern}' has high execution time variance "
                        f"(min: {min_time}ms, max: {max_time}ms). "
                        "This might indicate missing indexes or data skew."
                    )

        # Check for frequent queries that could benefit from caching
        if "top_query_patterns" in stats:
            for pattern_stat in stats["top_query_patterns"]:
                if pattern_stat["count"] > 100 and pattern_stat["avg_time_ms"] > 50:
                    pattern = pattern_stat["pattern"][:50] + "..."
                    count = pattern_stat["count"]
                    avg_time = pattern_stat["avg_time_ms"]
                    recommendations.append(
                        f"Frequently executed query '{pattern}' "
                        f"(count: {count}, avg: {avg_time}ms) "
                        "could benefit from result caching."
                    )

        if not recommendations:
            recommendations.append("Query performance appears to be within acceptable ranges.")

        return recommendations
