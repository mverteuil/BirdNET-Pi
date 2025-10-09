"""Verify that IOC database integration works with test fixtures."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from birdnetpi.detections.models import Detection
from birdnetpi.web.core.container import Container


@pytest.mark.asyncio
async def test_ioc_database_accessible_in_tests(app_with_temp_data):
    """Should verify that IOC database can be accessed in integration tests."""
    # Get the species database service
    species_db = Container.species_database()
    core_db = Container.core_database()

    async with core_db.get_async_db() as session:
        # Attach IOC database
        await species_db.attach_all_to_session(session)

        # Try to query the IOC database
        result = await session.execute(
            text("SELECT scientific_name, english_name, family FROM ioc.species LIMIT 5")
        )
        rows = result.fetchall()

        # Verify we got results
        assert len(rows) > 0, "Should be able to query IOC database"
        print("\nIOC database rows:")
        for row in rows:
            print(f"  {row.scientific_name}: {row.english_name} (Family: {row.family})")


@pytest.mark.asyncio
async def test_detection_query_service_with_taxa(app_with_temp_data, model_factory):
    """Should verify that DetectionQueryService can query with taxa."""
    # Get services
    db_service = app_with_temp_data._test_db_service
    query_service = Container.detection_query_service()

    # Debug: Check if they're using the same database
    print(f"\ndb_service database path: {db_service.db_path}")
    print(f"query_service database path: {query_service.core_database.db_path}")
    print(f"Are they the same service? {db_service is query_service.core_database}")

    # Create a detection
    async with db_service.get_async_db() as session:
        robin = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            species_tensor="Turdus migratorius_American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 1, 8, 30, 0, tzinfo=UTC),
        )
        session.add(robin)
        await session.commit()
        await session.refresh(robin)
        robin_id = robin.id

    # Verify detection exists in database
    async with db_service.get_async_db() as session:
        result = await session.execute(select(Detection).where(Detection.id == robin_id))
        found = result.scalar_one_or_none()
        print(f"\nDetection in database: {found}")
        print(f"  ID type: {type(robin_id)}, ID value: {robin_id}")

    # Try the raw SQL query first
    async with db_service.get_async_db() as session:
        # Attach IOC database
        species_db = Container.species_database()
        await species_db.attach_all_to_session(session)

        # Check how ID is actually stored in SQLite
        all_ids_query = text("SELECT id FROM detections")
        all_result = await session.execute(all_ids_query)
        all_ids = all_result.fetchall()
        print(f"\nAll IDs in database: {all_ids}")
        if all_ids:
            print(f"  First ID type: {type(all_ids[0][0])}, value: {all_ids[0][0]}")

        # Try the exact query used by get_detection_with_taxa
        query_sql = text("""
            SELECT
                d.id,
                d.species_tensor,
                d.scientific_name
            FROM detections d
            WHERE d.id = :detection_id
        """)

        # Try different formats for the UUID parameter
        print(f"\nTrying str(robin_id): {robin_id!s}")
        result = await session.execute(query_sql, {"detection_id": str(robin_id)})
        row = result.fetchone()
        print(f"  Result: {row}")

        print(f"\nTrying robin_id.hex: {robin_id.hex}")
        result2 = await session.execute(query_sql, {"detection_id": robin_id.hex})
        row2 = result2.fetchone()
        print(f"  Result: {row2}")

    # Try to get it with taxa
    print(f"\nCalling get_detection_with_taxa with ID: {robin_id}")
    detection_with_taxa = await query_service.get_detection_with_taxa(robin_id)
    print(f"Result: {detection_with_taxa}")

    # Verify result
    assert detection_with_taxa is not None, "Should find detection with taxa"
    assert detection_with_taxa.id == robin_id
    assert detection_with_taxa.scientific_name == "Turdus migratorius"
    print(f"\nDetection with taxa: {detection_with_taxa}")
    print(f"  Family: {detection_with_taxa.family}")
    print(f"  Genus: {detection_with_taxa.genus}")
    print(f"  IOC English: {detection_with_taxa.ioc_english_name}")
