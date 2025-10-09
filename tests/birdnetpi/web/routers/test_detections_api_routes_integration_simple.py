"""Simplified integration tests for detections API routes.

This file demonstrates integration testing within current constraints:
- Tests core CRUD operations that don't require IOC database
- Verifies request→router→service→database→response flow
- Focuses on HTTP layer and basic data persistence

NOTE: Full integration testing requires IOC reference database setup.
Tests requiring taxonomy joins are marked and documented separately.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def app_with_detections(app_with_temp_data, model_factory):
    """FastAPI app with 3 pre-seeded detections in its database."""
    db_service = app_with_temp_data._test_db_service
    async with db_service.get_async_db() as session:
        # Add 3 known detections
        robin = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            species_tensor="Turdus migratorius_American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 1, 8, 30, 0, tzinfo=UTC),
        )
        crow = model_factory.create_detection(
            scientific_name="Corvus brachyrhynchos",
            common_name="American Crow",
            species_tensor="Corvus brachyrhynchos_American Crow",
            confidence=0.88,
            timestamp=datetime(2025, 1, 1, 9, 15, 0, tzinfo=UTC),
        )
        cardinal = model_factory.create_detection(
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            species_tensor="Cardinalis cardinalis_Northern Cardinal",
            confidence=0.92,
            timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
        )
        session.add(robin)
        session.add(crow)
        session.add(cardinal)
        await session.commit()

    yield app_with_temp_data


class TestBasicDetectionCRUD:
    """Integration tests for basic detection operations."""

    async def test_get_recent_detections_from_real_database(self, app_with_detections):
        """Should retrieve recent detections from actual database."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            response = await client.get("/api/detections/recent?limit=10")

            assert response.status_code == 200
            data = response.json()

            # Verify we got the 3 detections
            assert data["count"] == 3
            assert len(data["detections"]) == 3

            # Verify actual data from database
            species = {d["common_name"] for d in data["detections"]}
            assert species == {"American Robin", "American Crow", "Northern Cardinal"}

    async def test_get_recent_detections_respects_limit(self, app_with_detections):
        """Should respect LIMIT parameter in SQL query."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            response = await client.get("/api/detections/recent?limit=2")

            assert response.status_code == 200
            data = response.json()

            # Should get exactly 2 most recent
            assert len(data["detections"]) == 2
            assert data["count"] == 2

    # POST test requires file I/O infrastructure not yet set up
    # See: tests requiring file system ops in TESTS REQUIRING IOC section below


class TestHTTPErrorHandling:
    """Integration tests for HTTP error responses."""

    async def test_handles_malformed_query_parameters(self, app_with_detections):
        """Should handle invalid query parameters gracefully."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Invalid page number
            response = await client.get("/api/detections/?page=0&per_page=-1")

            # Should either validate (422) or use defaults (200)
            assert response.status_code in [200, 422]


class TestDataConsistency:
    """Integration tests for data integrity."""

    async def test_concurrent_reads_dont_corrupt_data(self, app_with_detections):
        """Should handle concurrent requests without data corruption."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Make multiple concurrent requests
            tasks = [
                client.get("/api/detections/recent?limit=10"),
                client.get("/api/detections/recent?limit=10"),
                client.get("/api/detections/recent?limit=10"),
            ]

            responses = await asyncio.gather(*tasks)

            # All should succeed
            assert all(r.status_code == 200 for r in responses)

            # All should return same data
            data_sets = [r.json()["count"] for r in responses]
            assert all(count == 3 for count in data_sets)


# Tests requiring additional infrastructure are documented here for future implementation
"""
TESTS REQUIRING ADDITIONAL INFRASTRUCTURE:

These tests cannot run with current test setup:

## File I/O Tests (require PathResolver fully mocked):

1. test_create_detection_via_post():
   - POST /api/detections/ saves audio files to disk
   - DataManager.create_detection() requires recordings directory
   - PathResolver overrides don't reach all file I/O paths
   - Solution: Mock FileManager or set up full temp directory structure

## IOC Reference Database Tests:

2. test_get_detection_by_id_with_taxa():
   - Requires IOC join for family/genus/order data
   - Endpoint: /api/detections/{detection_id}

3. test_get_detection_count_by_date():
   - count_by_date() query expects specific result structure
   - Endpoint: /api/detections/count

4. test_paginated_detections_with_filters():
   - Pagination with taxonomy filters requires IOC data
   - Endpoint: /api/detections/?family=...&genus=...

5. test_species_summary_with_aggregation():
   - Species summary aggregates taxonomy fields from IOC
   - Endpoint: /api/detections/species/summary

6. test_taxonomy_hierarchy_queries():
   - Family/genus/species endpoints query IOC database
   - Endpoints: /api/detections/taxonomy/*

Future work: Create IOC database fixture + mock file I/O.
"""
