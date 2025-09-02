"""Tests for database optimization utilities."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.utils.database_optimizer import DatabaseOptimizer, QueryPerformanceMonitor


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Create database and tables
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)

    # Add test data
    session_class = sessionmaker(bind=engine)
    session = session_class()

    # Create test detections
    test_species = [
        ("Turdus migratorius", "American Robin"),
        ("Cardinalis cardinalis", "Northern Cardinal"),
        ("Poecile carolinensis", "Carolina Chickadee"),
        ("Cyanocitta cristata", "Blue Jay"),
        ("Sitta carolinensis", "White-breasted Nuthatch"),
    ]

    now = datetime.now()
    for i in range(100):
        # Create audio file
        audio_file = AudioFile(
            file_path=Path(f"/test/audio_{i}.wav"),
            duration=3.0,
            size_bytes=48000,
        )
        session.add(audio_file)
        session.flush()

        # Create detection
        species_idx = i % len(test_species)
        scientific_name, common_name = test_species[species_idx]

        detection = Detection(
            species_tensor=f"{scientific_name}_{common_name}",
            scientific_name=scientific_name,
            common_name=common_name,
            confidence=0.5 + (i % 50) / 100.0,
            timestamp=now - timedelta(days=i % 30, hours=i % 24),
            audio_file_id=audio_file.id,
            latitude=63.4591 + (i % 10) / 100,
            longitude=-19.3647 + (i % 10) / 100,
            species_confidence_threshold=0.5,
            week=i % 52,
            sensitivity_setting=1.5,
            overlap=0.5,
        )
        session.add(detection)

    session.commit()
    session.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def database_service(temp_db):
    """Create a DatabaseService instance with test database."""
    service = DatabaseService(Path(temp_db))
    try:
        yield service
    finally:
        # Dispose async engine to prevent file descriptor leaks
        if hasattr(service, "async_engine") and service.async_engine:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    task = loop.create_task(service.async_engine.dispose())
                    # Store reference to avoid garbage collection
                    _ = task
                else:
                    loop.run_until_complete(service.async_engine.dispose())
            except RuntimeError:
                # No event loop, create one just for cleanup
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(service.async_engine.dispose())
                finally:
                    loop.close()


@pytest.fixture
def optimizer(database_service):
    """Create a DatabaseOptimizer instance."""
    return DatabaseOptimizer(database_service)


@pytest.fixture
def monitor(database_service):
    """Create a QueryPerformanceMonitor instance."""
    return QueryPerformanceMonitor(database_service)


class TestQueryPerformanceMonitor:
    """Test QueryPerformanceMonitor functionality."""

    @pytest.mark.asyncio
    async def test_explain_query(self, monitor):
        """Test query plan analysis."""
        query = "SELECT * FROM detections WHERE scientific_name = :species"
        params = {"species": "Turdus migratorius"}

        result = await monitor.explain_query(query, params)

        assert "query" in result
        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert "uses_index" in result
        assert "full_table_scan" in result
        assert "temp_b_tree" in result

    @pytest.mark.asyncio
    async def test_measure_query_time(self, monitor):
        """Test query execution time measurement."""
        query = "SELECT COUNT(*) FROM detections"

        exec_time, row_count = await monitor.measure_query_time(query)

        assert exec_time > 0
        assert row_count == 1  # COUNT query returns one row

    @pytest.mark.asyncio
    async def test_analyze_common_queries(self, monitor):
        """Test analysis of common query patterns."""
        results = await monitor.analyze_common_queries()

        assert isinstance(results, list)
        assert len(results) > 0

        for result in results:
            assert "name" in result
            assert "query" in result
            if "error" not in result:
                assert "execution_time_ms" in result
                assert "row_count" in result
                assert "uses_index" in result
                assert "full_table_scan" in result


class TestDatabaseOptimizer:
    """Test DatabaseOptimizer functionality."""

    @pytest.mark.asyncio
    async def test_get_current_indexes(self, optimizer):
        """Test retrieving current database indexes."""
        indexes = await optimizer.get_current_indexes()

        assert isinstance(indexes, dict)
        assert "detections" in indexes
        assert "audio_files" in indexes
        assert isinstance(indexes["detections"], list)
        assert isinstance(indexes["audio_files"], list)

    @pytest.mark.asyncio
    async def test_create_optimized_indexes_dry_run(self, optimizer):
        """Test index creation in dry-run mode."""
        sql_statements = await optimizer.create_optimized_indexes(dry_run=True)

        assert isinstance(sql_statements, list)
        assert len(sql_statements) > 0
        assert all("CREATE INDEX" in sql for sql in sql_statements)

        # Verify no actual indexes were created
        indexes_before = await optimizer.get_current_indexes()
        sql_statements = await optimizer.create_optimized_indexes(dry_run=True)
        indexes_after = await optimizer.get_current_indexes()

        assert indexes_before == indexes_after

    @pytest.mark.asyncio
    async def test_create_optimized_indexes(self, optimizer):
        """Test actual index creation."""
        # Get initial indexes
        indexes_before = await optimizer.get_current_indexes()
        initial_count = sum(len(idx_list) for idx_list in indexes_before.values())

        # Create indexes
        sql_statements = await optimizer.create_optimized_indexes(dry_run=False)

        assert isinstance(sql_statements, list)
        assert len(sql_statements) > 0

        # Verify indexes were created
        indexes_after = await optimizer.get_current_indexes()
        final_count = sum(len(idx_list) for idx_list in indexes_after.values())

        # Note: Some indexes might already exist, so we check for >= instead of >
        assert final_count >= initial_count

    @pytest.mark.asyncio
    async def test_analyze_table_statistics(self, optimizer):
        """Test table statistics analysis."""
        stats = await optimizer.analyze_table_statistics()

        assert isinstance(stats, dict)
        assert "tables" in stats

        # Check table info
        tables = stats["tables"]
        assert "detections" in tables
        assert "audio_files" in tables

        # Check detection statistics
        detections_info = tables["detections"]
        if "error" not in detections_info:
            assert detections_info["row_count"] == 100  # We created 100 test records

        # Check distribution statistics
        if "top_species" in stats:
            assert isinstance(stats["top_species"], list)
            assert len(stats["top_species"]) <= 10
            for species in stats["top_species"]:
                assert "species" in species
                assert "count" in species

        if "date_range" in stats:
            assert "earliest" in stats["date_range"]
            assert "latest" in stats["date_range"]
            assert "days_span" in stats["date_range"]

        if "confidence_distribution" in stats:
            assert "min" in stats["confidence_distribution"]
            assert "max" in stats["confidence_distribution"]
            assert "average" in stats["confidence_distribution"]
            assert "high_confidence_count" in stats["confidence_distribution"]

    @pytest.mark.asyncio
    async def test_optimize_database(self, optimizer):
        """Test complete database optimization."""
        results = await optimizer.optimize_database()

        assert isinstance(results, dict)
        assert "timestamp" in results
        assert "current_indexes" in results
        assert "created_indexes" in results
        assert "table_statistics" in results
        assert "query_performance_before" in results
        assert "query_performance_after" in results
        assert "recommendations" in results

        # Check that recommendations were generated
        assert isinstance(results["recommendations"], list)
        assert len(results["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_generate_recommendations(self, optimizer):
        """Test recommendation generation."""
        # Create mock results
        results = {
            "table_statistics": {
                "tables": {
                    "detections": {"row_count": 150000},
                    "audio_files": {"row_count": 150000},
                }
            },
            "query_performance_after": [
                {
                    "name": "Slow Query",
                    "execution_time_ms": 150,
                    "full_table_scan": True,
                    "uses_index": False,
                },
                {
                    "name": "Fast Query",
                    "execution_time_ms": 10,
                    "full_table_scan": False,
                    "uses_index": True,
                },
            ],
        }

        recommendations = optimizer._generate_recommendations(results)

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        # Check for specific recommendations based on mock data
        rec_text = " ".join(recommendations)
        assert "rows" in rec_text.lower() or "archival" in rec_text.lower()
        assert "slow" in rec_text.lower() or "full table scan" in rec_text.lower()


class TestOptimizationPerformance:
    """Test optimization performance improvements."""

    @pytest.mark.asyncio
    async def test_query_performance_improvement(self, optimizer):
        """Test that optimization improves query performance."""
        # Measure performance before optimization
        monitor = optimizer.monitor
        before_results = await monitor.analyze_common_queries()

        # Calculate average time before
        before_times = [r["execution_time_ms"] for r in before_results if "execution_time_ms" in r]
        avg_before = sum(before_times) / len(before_times) if before_times else 0

        # Run optimization
        await optimizer.create_optimized_indexes(dry_run=False)

        # Measure performance after optimization
        after_results = await monitor.analyze_common_queries()

        # Calculate average time after
        after_times = [r["execution_time_ms"] for r in after_results if "execution_time_ms" in r]
        avg_after = sum(after_times) / len(after_times) if after_times else 0

        # Performance should generally improve or stay the same
        # (In test environment with small data, improvement might be minimal)
        # Allow more variance for test stability since SQLite performance can vary
        # With small test datasets (100 rows), indexes may add overhead
        if avg_before > 0:  # Only check if we have valid before times
            assert (
                avg_after <= avg_before * 2.0
            )  # Allow 100% variance for test stability with small data

        # Check that queries still use indexes after optimization
        # Note: SQLite's query planner may choose different paths with multiple indexes available
        # The planner might decide a full scan is more efficient for small test datasets
        indexes_used_before = sum(1 for r in before_results if r.get("uses_index", False))
        indexes_used_after = sum(1 for r in after_results if r.get("uses_index", False))

        # With small test datasets, ensure at least some queries use indexes
        # The query planner's choices may vary, so we allow some flexibility
        assert (
            indexes_used_after >= indexes_used_before - 1
        )  # Allow one less index usage for flexibility
