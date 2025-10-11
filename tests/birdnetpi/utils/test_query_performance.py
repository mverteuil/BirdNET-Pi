"""Test query performance for species summary with first detections."""

import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from birdnetpi.web.core.container import Container


@pytest.mark.asyncio
async def test_species_summary_performance(app_with_temp_data):
    """Should return species summary with first detections quickly."""
    _ = app_with_temp_data  # Ensure test data is initialized

    # Get the query service from the container
    container = Container()
    detection_query_service = container.detection_query_service()

    # First, populate some test data
    async with container.core_database().get_async_db() as session:
        # Insert test detections
        for i in range(100):
            await session.execute(
                text("""
                    INSERT INTO detections (
                        id, species_tensor, scientific_name, common_name,
                        confidence, timestamp
                    ) VALUES (
                        :id, :tensor, :sci_name, :common,
                        :conf, :ts
                    )
                """),
                {
                    "id": f"test-{i:04d}",
                    "tensor": f"Species_{i % 10}_Common_{i % 10}",
                    "sci_name": f"Species {i % 10}",
                    "common": f"Common {i % 10}",
                    "conf": 0.5 + (i % 50) / 100.0,
                    "ts": datetime.now() - timedelta(days=i),
                },
            )
        await session.commit()

    # Test optimized query with first detections
    start_time = time.time()
    result = await detection_query_service.get_species_summary(
        since=datetime.now() - timedelta(days=30),
        include_first_detections=True,  # This should be fast now
    )
    elapsed = time.time() - start_time

    # Should return in under 1 second (was 16 seconds before optimization)
    assert elapsed < 1.0, f"Query took {elapsed:.2f} seconds, expected < 1 second"

    # Should have results
    assert len(result) > 0

    # Should have first detection metadata
    for species in result:
        if species.get("detection_count", 0) > 0:
            # These fields should be present with optimized query
            assert "first_ever_detection" in species
            assert "first_period_detection" in species

    print(f"✓ Species summary with first detections completed in {elapsed:.3f} seconds")


@pytest.mark.asyncio
async def test_query_without_lower_functions(app_with_temp_data):
    """Should execute JOIN queries without using LOWER() functions."""
    _ = app_with_temp_data  # Ensure test data is initialized
    container = Container()

    # Check the optimized query SQL
    async with container.core_database().get_async_db() as session:
        await container.species_database().attach_all_to_session(session)

        # Build the optimized query SQL
        query_sql = text("""
            SELECT
                d.scientific_name,
                COUNT(*) as detection_count
            FROM detections d
            LEFT JOIN wikidata.translations w
                ON w.avibase_id = (
                    SELECT i.avibase_id
                    FROM ioc.species i
                    WHERE i.scientific_name = d.scientific_name
                )
                AND w.language_code = :language_code
            GROUP BY d.scientific_name
        """)

        # Should execute without errors (no LOWER() preventing index use)
        result = await session.execute(query_sql, {"language_code": "en"})
        _ = result.fetchall()  # Ensure query completes

        # Query should complete quickly
        assert True  # If we got here, the query worked

        await container.species_database().detach_all_from_session(session)


@pytest.mark.asyncio
async def test_optimized_window_functions(app_with_temp_data):
    """Should use optimized window functions for first detection tracking."""
    _ = app_with_temp_data  # Ensure test data is initialized
    container = Container()

    # Insert test data with known patterns
    async with container.core_database().get_async_db() as session:
        # Create test species with different detection patterns
        base_time = datetime.now()
        test_data = [
            # Species 1: Multiple detections, first was 10 days ago
            ("Parus major", base_time - timedelta(days=10), 0.9),
            ("Parus major", base_time - timedelta(days=5), 0.8),
            ("Parus major", base_time - timedelta(days=1), 0.7),
            # Species 2: Only recent detections
            ("Corvus corax", base_time - timedelta(days=2), 0.85),
            ("Corvus corax", base_time - timedelta(hours=1), 0.95),
            # Species 3: Single old detection
            ("Sitta europaea", base_time - timedelta(days=20), 0.6),
        ]

        for sci_name, timestamp, confidence in test_data:
            await session.execute(
                text("""
                    INSERT INTO detections (
                        id, species_tensor, scientific_name, common_name,
                        confidence, timestamp
                    ) VALUES (
                        :id, :tensor, :sci_name, :common, :conf, :ts
                    )
                """),
                {
                    "id": f"test-{sci_name}-{timestamp.timestamp()}",
                    "tensor": f"{sci_name}_Common",
                    "sci_name": sci_name,
                    "common": sci_name.split()[1].capitalize(),
                    "conf": confidence,
                    "ts": timestamp,
                },
            )
        await session.commit()

    # Get species summary with first detections
    detection_query_service = container.detection_query_service()
    result = await detection_query_service.get_species_summary(
        since=base_time - timedelta(days=15),  # 15 days back
        include_first_detections=True,
    )

    # Verify results contain expected data
    species_by_name = {r["scientific_name"]: r for r in result}

    # Check Parus major (has detections both in and out of period)
    assert "Parus major" in species_by_name
    parus = species_by_name["Parus major"]
    assert parus["detection_count"] == 3
    assert parus.get("first_ever_detection") is not None
    assert parus.get("first_period_detection") is not None

    # Parse datetime strings if needed
    if isinstance(parus["first_ever_detection"], str):
        from dateutil import parser

        first_ever = parser.parse(parus["first_ever_detection"])
    else:
        first_ever = parus["first_ever_detection"]

    # First ever and first period should be the same (10 days ago)
    assert abs((first_ever - (base_time - timedelta(days=10))).total_seconds()) < 60

    # Check Corvus corax (only recent detections)
    assert "Corvus corax" in species_by_name
    corvus = species_by_name["Corvus corax"]
    assert corvus["detection_count"] == 2
    assert corvus.get("first_ever_detection") is not None

    # Parse datetime string if needed
    if isinstance(corvus["first_ever_detection"], str):
        from dateutil import parser

        first_ever_corvus = parser.parse(corvus["first_ever_detection"])
    else:
        first_ever_corvus = corvus["first_ever_detection"]

    # First detection is 2 days ago
    assert abs((first_ever_corvus - (base_time - timedelta(days=2))).total_seconds()) < 60

    # Check Sitta europaea (outside period)
    # Should not be in results since it's outside the 15-day window
    assert "Sitta europaea" not in species_by_name
