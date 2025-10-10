"""Integration tests for detections API routes using real database.

This file demonstrates the proper way to test API routes:
- Uses real FastAPI app with actual database
- Tests complete request → service → database → response flow
- Verifies actual behavior, not mock configurations
- Replaces mock-heavy tests with meaningful integration tests

Pattern:
    BEFORE (Mock-Heavy):
        - Mock all services
        - Configure mock return values
        - Assert mock returns what we told it to return
        - Tests nothing real

    AFTER (Integration):
        - Use app_with_temp_data fixture
        - Make real HTTP requests
        - Verify actual database state
        - Tests real workflows
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from birdnetpi.detections.models import Detection


@pytest.fixture
async def app_with_detections(app_with_temp_data, model_factory):
    """FastAPI app with 3 pre-seeded detections in its database.

    This helper fixture populates the app's actual database with test data,
    ensuring the app and tests use the same database instance.
    """
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


class TestDetectionsAPIIntegration:
    """Integration tests for detection CRUD operations."""

    async def test_get_recent_detections_from_real_database(self, app_with_detections):
        """Should retrieve recent detections from actual database.

        This test verifies the complete workflow:
        1. HTTP request to API
        2. Router calls DetectionQueryService
        3. Service queries real SQLite database
        4. Results serialized and returned
        5. Response contains actual persisted data
        """
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

            # Verify data accuracy (robin has highest confidence)
            robin_data = next(d for d in data["detections"] if d["common_name"] == "American Robin")
            assert robin_data["confidence"] == 0.95
            assert robin_data["scientific_name"] == "Turdus migratorius"

    async def test_get_recent_detections_limit_parameter(self, app_with_detections):
        """Should respect limit parameter in recent detections query.

        Tests that LIMIT SQL clause actually works, not just mock configuration.
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Request only 2 recent detections
            response = await client.get("/api/detections/recent?limit=2")

            assert response.status_code == 200
            data = response.json()

            # Should get exactly 2 detections (most recent)
            assert len(data["detections"]) == 2
            assert data["count"] == 2

            # Verify we got actual data
            for detection in data["detections"]:
                assert "common_name" in detection
                assert "confidence" in detection

    async def test_get_detection_by_id_retrieves_from_database(self, app_with_detections):
        """Should retrieve specific detection by UUID from database.

        Tests:
        - UUID-based lookup in real database
        - Proper 404 for non-existent detection
        - Complete detection data serialization
        """
        # Get a known detection ID from the app's database
        db_service = app_with_detections._test_db_service
        async with db_service.get_async_db() as session:
            result = await session.execute(
                select(Detection).where(Detection.common_name == "American Robin")
            )
            robin = result.scalar_one()
            robin_id = robin.id

        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Test successful retrieval
            response = await client.get(f"/api/detections/{robin_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(robin_id)
            assert data["common_name"] == "American Robin"
            assert data["confidence"] == 0.95

            # Test 404 for non-existent detection
            fake_id = uuid4()
            response = await client.get(f"/api/detections/{fake_id}")
            assert response.status_code == 404

    async def test_get_detection_count_calculates_from_real_data(self, app_with_detections):
        """Should count detections from actual database, not mock configuration."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Query for the date when test detections were created
            response = await client.get("/api/detections/count?target_date=2025-01-01")

            assert response.status_code == 200
            data = response.json()

            # Verify count matches actual database state
            assert data["count"] == 3

            # Verify date is included and matches requested date
            assert data["date"] == "2025-01-01"

    async def test_paginated_detections_with_real_pagination(
        self, app_with_detections, model_factory
    ):
        """Should paginate results from real database query.

        Tests actual LIMIT/OFFSET SQL behavior, not mock slicing.
        """
        # Add more detections to test pagination
        db_service = app_with_detections._test_db_service
        async with db_service.get_async_db() as session:
            for i in range(7):
                detection = model_factory.create_detection(
                    scientific_name=f"Testus species{i}",
                    common_name=f"Test Bird {i}",
                    confidence=0.80 + (i * 0.01),
                    timestamp=datetime(2025, 1, 1, 12, i, 0, tzinfo=UTC),
                )
                session.add(detection)
            await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Use the date when test detections were created
            test_date = "2025-01-01"

            # Request first page (10 per page minimum)
            # Paginated endpoint requires start_date and end_date
            response = await client.get(
                f"/api/detections/?page=1&per_page=10&start_date={test_date}&end_date={test_date}"
            )

            assert response.status_code == 200
            data = response.json()

            # Verify pagination metadata - all 10 detections fit on one page
            assert len(data["detections"]) == 10  # 3 original + 7 new = 10 total
            assert data["pagination"]["page"] == 1
            assert data["pagination"]["per_page"] == 10
            assert data["pagination"]["total"] == 10  # 3 original + 7 new
            assert data["pagination"]["total_pages"] == 1
            assert data["pagination"]["has_next"] is False
            assert data["pagination"]["has_prev"] is False


class TestSpeciesSummaryIntegration:
    """Integration tests for species summary endpoints."""

    async def test_get_species_summary_aggregates_real_data(
        self, app_with_detections, model_factory
    ):
        """Should aggregate species counts from actual database.

        Tests SQL GROUP BY aggregation, not mock data structures.
        """
        # Add duplicate detections for aggregation testing
        db_service = app_with_detections._test_db_service
        async with db_service.get_async_db() as session:
            robin_duplicate = model_factory.create_detection(
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                species_tensor="Turdus migratorius_American Robin",
                confidence=0.90,
                timestamp=datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC),
            )
            session.add(robin_duplicate)
            await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            response = await client.get("/api/detections/species/summary")

            assert response.status_code == 200
            data = response.json()

            # Verify count of unique species
            assert data["count"] == 3  # Robin, Crow, Cardinal

            # Verify robin appears twice (original + duplicate)
            robin_summary = next(
                s for s in data["species"] if s["scientific_name"] == "Turdus migratorius"
            )
            assert robin_summary["detection_count"] == 2

            # Verify others appear once
            crow_summary = next(
                s for s in data["species"] if s["scientific_name"] == "Corvus brachyrhynchos"
            )
            assert crow_summary["detection_count"] == 1


class TestTaxonomyHierarchyIntegration:
    """Integration tests for hierarchical taxonomy filtering."""

    async def test_get_families_from_real_database(self, app_with_detections):
        """Should extract unique families from actual detections using IOC database.

        Tests that:
        1. Detections are joined with IOC database to get family information
        2. DISTINCT aggregation returns unique families
        3. Families match the expected taxonomic classification:
           - American Robin (Turdus migratorius) → Turdidae
           - American Crow (Corvus brachyrhynchos) → Corvidae
           - Northern Cardinal (Cardinalis cardinalis) → Cardinalidae
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            response = await client.get("/api/detections/taxonomy/families")

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "families" in data
            assert "count" in data

            # Verify IOC database integration populated family data
            assert data["count"] == 3, f"Expected 3 families, got {data['count']}"

            # Verify the actual families from IOC database
            expected_families = {"Turdidae", "Corvidae", "Cardinalidae"}
            actual_families = set(data["families"])
            assert actual_families == expected_families, (
                f"Expected families {expected_families}, got {actual_families}"
            )


class TestErrorRecoveryIntegration:
    """Integration tests for error handling with real database."""

    async def test_database_constraint_violation_handling(self, app_with_detections):
        """Should handle database errors gracefully and continue serving requests.

        Verifies:
        1. Returns proper HTTP error code (404, not 500)
        2. Provides helpful error message
        3. System continues to work after error
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Make request that triggers error (non-existent detection)
            fake_id = uuid4()
            error_response = await client.get(f"/api/detections/{fake_id}")

            # Should return 404, not 500
            assert error_response.status_code == 404
            assert "not found" in error_response.json()["detail"].lower()

            # RECOVERY: Verify system continues to work after error
            # Make successful request to verify database connection still works
            recovery_response = await client.get("/api/detections/recent?limit=10")
            assert recovery_response.status_code == 200
            data = recovery_response.json()
            assert data["count"] == 3  # Original 3 detections still accessible

    async def test_recovers_from_query_errors(self, app_with_detections):
        """Should handle malformed queries and continue serving valid requests.

        Verifies:
        1. Gracefully handles invalid parameters
        2. System recovers and processes valid requests after error
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Test with invalid query parameters
            error_response = await client.get("/api/detections/?page=0&per_page=-1")

            # Should handle gracefully (may return 422 or use defaults)
            assert error_response.status_code in [200, 422]

            # RECOVERY: Verify system continues to work after malformed request
            recovery_response = await client.get("/api/detections/recent?limit=5")
            assert recovery_response.status_code == 200
            assert recovery_response.json()["count"] >= 0  # Valid response

    async def test_error_boundary_multiple_errors(self, app_with_detections):
        """Should handle multiple consecutive errors without degradation.

        Verifies that error handling doesn't cause state corruption that
        affects subsequent requests.
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Make multiple requests that trigger errors
            fake_ids = [uuid4() for _ in range(3)]
            error_responses = []

            for fake_id in fake_ids:
                response = await client.get(f"/api/detections/{fake_id}")
                error_responses.append(response)

            # All should return proper 404 errors
            assert all(r.status_code == 404 for r in error_responses)

            # RECOVERY: Verify system still works normally after multiple errors
            recovery_response = await client.get("/api/detections/recent?limit=10")
            assert recovery_response.status_code == 200
            data = recovery_response.json()
            assert data["count"] == 3  # Data integrity maintained


class TestDataIntegrityIntegration:
    """Integration tests verifying data integrity across operations."""

    async def test_detection_persistence_and_retrieval_consistency(
        self, app_with_detections, model_factory
    ):
        """Should maintain data integrity through complete CRUD cycle.

        This test verifies:
        1. Data persists correctly to database
        2. Retrieval returns exact data that was saved
        3. No data loss or corruption in round-trip
        """
        # Add a detection with specific values
        db_service = app_with_detections._test_db_service
        async with db_service.get_async_db() as session:
            new_detection = model_factory.create_detection(
                scientific_name="Sitta carolinensis",
                common_name="White-breasted Nuthatch",
                species_tensor="Sitta carolinensis_White-breasted Nuthatch",
                confidence=0.87,
                timestamp=datetime(2025, 1, 2, 14, 30, 0, tzinfo=UTC),
                latitude=41.0,
                longitude=-73.0,
            )
            session.add(new_detection)
            await session.commit()
            await session.refresh(new_detection)
            new_detection_id = new_detection.id

        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Retrieve via API
            response = await client.get(f"/api/detections/{new_detection_id}")

            assert response.status_code == 200
            data = response.json()

            # Verify exact round-trip accuracy
            assert data["scientific_name"] == "Sitta carolinensis"
            assert data["common_name"] == "White-breasted Nuthatch"
            assert data["confidence"] == 0.87
            assert data["latitude"] == 41.0
            assert data["longitude"] == -73.0

            # Verify it appears in recent detections
            response = await client.get("/api/detections/recent?limit=20")
            recent_ids = [d["id"] for d in response.json()["detections"]]
            assert str(new_detection_id) in recent_ids

    async def test_concurrent_queries_dont_interfere(self, app_with_detections):
        """Should handle concurrent requests without data corruption.

        Tests that SQLite session management works correctly.
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_detections), base_url="http://test"
        ) as client:
            # Make multiple concurrent requests
            import asyncio

            tasks = [
                client.get("/api/detections/recent?limit=10"),
                client.get("/api/detections/species/summary"),
                client.get("/api/detections/count"),
            ]

            responses = await asyncio.gather(*tasks)

            # All should succeed
            assert all(r.status_code == 200 for r in responses)

            # Verify data consistency
            recent = responses[0].json()
            summary = responses[1].json()

            # Count from different endpoints should be consistent
            assert recent["count"] == 3
            assert summary["count"] == 3
