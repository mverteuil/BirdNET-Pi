"""Database optimization utilities for analytics queries.

This module provides tools to analyze query performance, create optimal indexes,
and monitor database health for the BirdNET-Pi application.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from birdnetpi.database.core import DatabaseService

logger = logging.getLogger(__name__)


class QueryPerformanceMonitor:
    """Monitor and analyze query performance for optimization recommendations."""

    def __init__(self, database_service: DatabaseService):
        """Initialize the query performance monitor.

        Args:
            database_service: Database service instance
        """
        self.database_service = database_service
        self.query_stats: list[dict[str, Any]] = []

    async def explain_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Analyze query execution plan using EXPLAIN QUERY PLAN.

        Args:
            query: SQL query to analyze
            params: Query parameters

        Returns:
            Dictionary containing query plan analysis
        """
        async with self.database_service.get_async_db() as session:
            # Get query plan
            explain_query = f"EXPLAIN QUERY PLAN {query}"
            result = await session.execute(text(explain_query), params or {})
            plan_rows = result.fetchall()

            # Analyze plan for optimization opportunities
            plan_analysis = {
                "query": query,
                "plan": [dict(row._mapping) for row in plan_rows],
                "uses_index": False,
                "full_table_scan": False,
                "temp_b_tree": False,
                "estimated_cost": 0,
            }

            for row in plan_rows:
                row_dict = dict(row._mapping)
                detail = row_dict.get("detail", "")

                if "USING INDEX" in detail:
                    plan_analysis["uses_index"] = True
                if "SCAN" in detail and "USING INDEX" not in detail:
                    plan_analysis["full_table_scan"] = True
                if "TEMP B-TREE" in detail:
                    plan_analysis["temp_b_tree"] = True

            return plan_analysis

    async def measure_query_time(
        self, query: str, params: dict[str, Any] | None = None, iterations: int = 3
    ) -> tuple[float, int]:
        """Measure average query execution time.

        Args:
            query: SQL query to measure
            params: Query parameters
            iterations: Number of iterations for averaging

        Returns:
            Tuple of (average_time_ms, row_count)
        """
        total_time = 0
        row_count = 0

        async with self.database_service.get_async_db() as session:
            # Warm up cache
            result = await session.execute(text(query), params or {})
            result.fetchall()

            # Measure execution time
            for _ in range(iterations):
                start = time.perf_counter()
                result = await session.execute(text(query), params or {})
                result = result.fetchall()
                elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
                total_time += elapsed
                row_count = len(result)

        return total_time / iterations, row_count

    async def analyze_common_queries(self) -> list[dict[str, Any]]:
        """Analyze performance of common analytics queries.

        Returns:
            List of query analysis results
        """
        common_queries = [
            # Date range queries
            {
                "name": "Date range query (last 7 days)",
                "query": """
                    SELECT * FROM detections
                    WHERE timestamp >= :start_date
                    ORDER BY timestamp DESC
                """,
                "params": {"start_date": datetime.now() - timedelta(days=7)},
            },
            # Species filtering
            {
                "name": "Species filter query",
                "query": """
                    SELECT * FROM detections
                    WHERE scientific_name = :species
                    ORDER BY timestamp DESC
                """,
                "params": {"species": "Turdus migratorius"},
            },
            # Aggregation queries
            {
                "name": "Species count aggregation",
                "query": """
                    SELECT scientific_name, COUNT(*) as count
                    FROM detections
                    WHERE timestamp >= :start_date
                    GROUP BY scientific_name
                    ORDER BY count DESC
                """,
                "params": {"start_date": datetime.now() - timedelta(days=30)},
            },
            # Complex join query (with IOC database)
            {
                "name": "Detection with species info join",
                "query": """
                    SELECT d.*, af.file_path, af.duration
                    FROM detections d
                    LEFT JOIN audio_files af ON d.audio_file_id = af.id
                    WHERE d.timestamp >= :start_date
                    ORDER BY d.timestamp DESC
                """,
                "params": {"start_date": datetime.now() - timedelta(days=7)},
            },
            # High confidence detections
            {
                "name": "High confidence detections",
                "query": """
                    SELECT * FROM detections
                    WHERE confidence > :min_confidence
                    ORDER BY confidence DESC, timestamp DESC
                """,
                "params": {"min_confidence": 0.8},
            },
            # Date and species combination
            {
                "name": "Date range with species filter",
                "query": """
                    SELECT * FROM detections
                    WHERE timestamp BETWEEN :start_date AND :end_date
                    AND scientific_name = :species
                    ORDER BY timestamp DESC
                """,
                "params": {
                    "start_date": datetime.now() - timedelta(days=30),
                    "end_date": datetime.now(),
                    "species": "Turdus migratorius",
                },
            },
        ]

        results = []
        for query_info in common_queries:
            try:
                # Analyze query plan
                plan = await self.explain_query(query_info["query"], query_info["params"])

                # Measure execution time
                exec_time, row_count = await self.measure_query_time(
                    query_info["query"], query_info["params"]
                )

                results.append(
                    {
                        "name": query_info["name"],
                        "execution_time_ms": round(exec_time, 2),
                        "row_count": row_count,
                        "uses_index": plan["uses_index"],
                        "full_table_scan": plan["full_table_scan"],
                        "temp_b_tree": plan["temp_b_tree"],
                        "query": query_info["query"].strip(),
                    }
                )
            except Exception as e:
                logger.error(f"Error analyzing query '{query_info['name']}': {e}")
                results.append(
                    {
                        "name": query_info["name"],
                        "error": str(e),
                        "query": query_info["query"].strip(),
                    }
                )

        return results


class DatabaseOptimizer:
    """Optimize database schema and indexes for analytics performance."""

    def __init__(self, database_service: DatabaseService):
        """Initialize the database optimizer.

        Args:
            database_service: Database service instance
        """
        self.database_service = database_service
        self.monitor = QueryPerformanceMonitor(database_service)

    async def get_current_indexes(self) -> dict[str, list[str]]:
        """Get current indexes for all tables.

        Returns:
            Dictionary mapping table names to list of index names
        """
        async with self.database_service.get_async_db() as session:
            # Use connection.run_sync for inspection with async engine
            conn = await session.connection()

            def _inspect_indexes(sync_conn: Connection) -> dict[str, list[str]]:
                inspector = inspect(sync_conn)
                indexes = {}

                for table_name in ["detections", "audio_files"]:
                    try:
                        table_indexes = inspector.get_indexes(table_name)
                        indexes[table_name] = [idx["name"] for idx in table_indexes if idx["name"]]
                    except Exception as e:
                        logger.error(f"Error getting indexes for {table_name}: {e}")
                        indexes[table_name] = []

                return indexes

            indexes = await conn.run_sync(_inspect_indexes)
            return indexes

    async def create_optimized_indexes(self, dry_run: bool = False) -> list[str]:
        """Create optimized indexes for analytics queries.

        Args:
            dry_run: If True, only return SQL statements without executing

        Returns:
            List of SQL statements executed or to be executed
        """
        sql_statements = []

        # Define optimized indexes based on common query patterns
        optimized_indexes = [
            # Single column indexes for most common filters
            "CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections(timestamp)",
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_scientific_name "
                "ON detections(scientific_name)"
            ),
            "CREATE INDEX IF NOT EXISTS idx_detections_confidence ON detections(confidence)",
            "CREATE INDEX IF NOT EXISTS idx_detections_common_name ON detections(common_name)",
            "CREATE INDEX IF NOT EXISTS idx_detections_week ON detections(week)",
            # Composite indexes for common query patterns
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_timestamp_species "
                "ON detections(timestamp, scientific_name)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_species_timestamp "
                "ON detections(scientific_name, timestamp)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_confidence_timestamp "
                "ON detections(confidence DESC, timestamp DESC)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_timestamp_confidence "
                "ON detections(timestamp DESC, confidence DESC)"
            ),
            # Covering index for species aggregation queries
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_species_stats "
                "ON detections(scientific_name, timestamp, confidence)"
            ),
            # Index for date range with species filter
            (
                "CREATE INDEX IF NOT EXISTS idx_detections_date_species_conf "
                "ON detections(timestamp, scientific_name, confidence)"
            ),
            # Audio files indexes
            "CREATE INDEX IF NOT EXISTS idx_audio_files_path ON audio_files(file_path)",
            "CREATE INDEX IF NOT EXISTS idx_audio_files_id ON audio_files(id)",
            # Foreign key index for joins
            "CREATE INDEX IF NOT EXISTS idx_detections_audio_file_id ON detections(audio_file_id)",
        ]

        if dry_run:
            return optimized_indexes

        # Execute index creation
        async with self.database_service.get_async_db() as session:
            for sql in optimized_indexes:
                try:
                    await session.execute(text(sql))
                    await session.commit()
                    sql_statements.append(sql)
                    logger.info(f"Created index: {sql}")
                except Exception as e:
                    logger.error(f"Error creating index: {e}")
                    await session.rollback()

        return sql_statements

    async def analyze_table_statistics(self) -> dict[str, Any]:
        """Analyze table statistics for optimization insights.

        Returns:
            Dictionary containing table statistics
        """
        stats = {}

        async with self.database_service.get_async_db() as session:
            # Get table sizes
            tables_info = {}
            for table_name in ["detections", "audio_files"]:
                try:
                    count_result = await session.execute(
                        text(f"SELECT COUNT(*) as count FROM {table_name}")
                    )
                    count_result = count_result.fetchone()
                    count = count_result[0] if count_result else 0

                    # Get table size in pages (SQLite specific)
                    page_count_result = await session.execute(
                        text(f"SELECT COUNT(*) FROM pragma_table_info('{table_name}')")
                    )
                    page_count_result = page_count_result.fetchone()

                    tables_info[table_name] = {
                        "row_count": count,
                        "columns": page_count_result[0] if page_count_result else 0,
                    }
                except Exception as e:
                    logger.error(f"Error analyzing table {table_name}: {e}")
                    tables_info[table_name] = {"error": str(e)}

            stats["tables"] = tables_info

            # Analyze data distribution for optimization hints
            try:
                # Species distribution
                species_dist = await session.execute(
                    text("""
                        SELECT scientific_name, COUNT(*) as count
                        FROM detections
                        GROUP BY scientific_name
                        ORDER BY count DESC
                        LIMIT 10
                    """)
                )
                species_dist = species_dist.fetchall()
                stats["top_species"] = [
                    {"species": row[0], "count": row[1]} for row in species_dist
                ]

                # Date range
                date_range = await session.execute(
                    text("""
                        SELECT
                            MIN(timestamp) as earliest,
                            MAX(timestamp) as latest,
                            julianday(MAX(timestamp)) - julianday(MIN(timestamp)) as days_span
                        FROM detections
                    """)
                )
                date_range = date_range.fetchone()
                if date_range:
                    earliest, latest, days_span_raw = date_range
                    stats["date_range"] = {
                        "earliest": earliest,
                        "latest": latest,
                        "days_span": round(float(days_span_raw), 1)
                        if days_span_raw is not None
                        else 0,
                    }

                # Confidence distribution
                conf_dist = await session.execute(
                    text("""
                        SELECT
                            MIN(confidence) as min_conf,
                            MAX(confidence) as max_conf,
                            AVG(confidence) as avg_conf,
                            COUNT(CASE WHEN confidence > 0.8 THEN 1 END) as high_conf_count
                        FROM detections
                    """)
                )
                conf_dist = conf_dist.fetchone()
                if conf_dist:
                    min_conf, max_conf, avg_conf, high_conf_count = conf_dist
                    stats["confidence_distribution"] = {
                        "min": round(float(min_conf), 3) if min_conf is not None else 0,
                        "max": round(float(max_conf), 3) if max_conf is not None else 0,
                        "average": round(float(avg_conf), 3) if avg_conf is not None else 0,
                        "high_confidence_count": high_conf_count or 0,
                    }

            except Exception as e:
                logger.error(f"Error analyzing data distribution: {e}")
                stats["distribution_error"] = str(e)

        return stats

    async def optimize_database(self) -> dict[str, Any]:
        """Run complete database optimization.

        Returns:
            Dictionary containing optimization results
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "current_indexes": {},
            "created_indexes": [],
            "table_statistics": {},
            "query_performance_before": [],
            "query_performance_after": [],
            "recommendations": [],
        }

        try:
            # Get current state
            results["current_indexes"] = await self.get_current_indexes()
            results["table_statistics"] = await self.analyze_table_statistics()

            # Analyze query performance before optimization
            logger.info("Analyzing query performance before optimization...")
            results["query_performance_before"] = await self.monitor.analyze_common_queries()

            # Create optimized indexes
            logger.info("Creating optimized indexes...")
            results["created_indexes"] = await self.create_optimized_indexes()

            # Run VACUUM to optimize database file
            logger.info("Running VACUUM to optimize database...")
            async with self.database_service.get_async_db() as session:
                await session.execute(text("VACUUM"))
                await session.commit()

            # Analyze query performance after optimization
            logger.info("Analyzing query performance after optimization...")
            results["query_performance_after"] = await self.monitor.analyze_common_queries()

            # Generate recommendations
            results["recommendations"] = self._generate_recommendations(results)

        except Exception as e:
            logger.error(f"Error during optimization: {e}")
            results["error"] = str(e)

        return results

    def _generate_recommendations(self, results: dict[str, Any]) -> list[str]:
        """Generate optimization recommendations based on analysis.

        Args:
            results: Optimization results dictionary

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Check table statistics
        stats = results.get("table_statistics", {})
        tables = stats.get("tables", {})

        for table_name, info in tables.items():
            if isinstance(info, dict) and "row_count" in info:
                if info["row_count"] > 100000:
                    recommendations.append(
                        f"Table '{table_name}' has {info['row_count']:,} rows. "
                        "Consider implementing data archival or partitioning strategy."
                    )

        # Check query performance
        after = results.get("query_performance_after", [])

        slow_queries = []
        for query in after:
            if "execution_time_ms" in query and query["execution_time_ms"] > 100:
                slow_queries.append(query["name"])

        if slow_queries:
            recommendations.append(
                f"The following queries are still slow (>100ms): {', '.join(slow_queries)}. "
                "Consider query optimization or caching strategies."
            )

        # Check for full table scans
        for query in after:
            if query.get("full_table_scan") and not query.get("uses_index"):
                recommendations.append(
                    f"Query '{query['name']}' performs full table scan. "
                    "Consider adding appropriate indexes."
                )

        # General recommendations
        if not recommendations:
            recommendations.append("Database is well-optimized for current query patterns.")

        recommendations.append("Run optimization periodically (monthly) to maintain performance.")
        recommendations.append("Monitor slow queries in production and adjust indexes accordingly.")

        return recommendations
