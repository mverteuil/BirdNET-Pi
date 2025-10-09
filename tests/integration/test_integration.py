"""Integration tests for the main application routes.

This file demonstrates proper integration testing:
- Uses the REAL FastAPI app (not a fake one)
- Tests actual routes with real dependencies
- Verifies actual behavior, not mock configurations

Pattern:
    BEFORE (No-Op):
        - Create fake app
        - Mock all dependencies
        - Test that mocks return what we configured
        - Tests nothing real

    AFTER (Integration):
        - Use app_with_temp_data fixture
        - Make real HTTP requests
        - Verify actual responses
        - Tests real workflows
"""

import pytest
from httpx import ASGITransport, AsyncClient


class TestMainRoutes:
    """Integration tests for main application routes."""

    @pytest.mark.asyncio
    async def test_api_endpoint_integration(self, app_with_temp_data):
        """Should make requests to real API endpoints and get valid responses."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_temp_data), base_url="http://test"
        ) as client:
            # Test a real API endpoint
            response = await client.get("/api/detections/recent?limit=10")

            # API should respond successfully
            assert response.status_code == 200
            data = response.json()

            # Verify response structure from actual endpoint
            assert "detections" in data
            assert "count" in data
            assert isinstance(data["detections"], list)
            assert isinstance(data["count"], int)

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, app_with_temp_data):
        """Should provide OpenAPI schema at /openapi.json."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_temp_data), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")

            # OpenAPI schema should be available
            assert response.status_code == 200
            schema = response.json()

            # Verify it's a valid OpenAPI schema
            assert "openapi" in schema
            assert "info" in schema
            assert "paths" in schema

    @pytest.mark.asyncio
    async def test_404_handling(self, app_with_temp_data):
        """Should return 404 for non-existent routes."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_temp_data), base_url="http://test"
        ) as client:
            response = await client.get("/this-route-does-not-exist")

            # Verify proper 404 handling
            assert response.status_code == 404
