"""Tests for analysis API routes."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.analysis_api_routes import router


@pytest.fixture
def client():
    """Create test client with analysis API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Create mock presentation manager
    mock_presentation_manager = AsyncMock(spec=PresentationManager)

    # Override PresentationManager with mock
    container.presentation_manager.override(mock_presentation_manager)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.analysis_api_routes"])

    # Include the router
    # Router already has prefix="/analysis", so we only add "/api"
    app.include_router(router, prefix="/api")

    # Create and return test client
    client = TestClient(app)

    # Store the mock for access in tests
    client.mock_presentation_manager = mock_presentation_manager  # type: ignore[attr-defined]

    return client


class TestAnalysisAPIRoutes:
    """Test analysis API endpoint."""

    def test_get_analysis_data_with_dates(self, client):
        """Should return analysis data for specified date range."""
        # Setup mock data
        mock_data = {
            "analyses": {
                "diversity": {"shannon": 2.5, "simpson": 0.8},
                "temporal": {"peak_hour": 6},
            },
            "summary": {"total_species": 42, "total_detections": 150},
            "generated_at": "2025-01-15T10:00:00Z",
        }

        # Don't re-spec methods on an already spec'd mock - just configure return values
        client.mock_presentation_manager.get_analysis_page_data.return_value = mock_data

        # Make request
        response = client.get(
            "/api/analysis?start_date=2025-01-01&end_date=2025-01-15&comparison=none"
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "analyses" in data
        assert "summary" in data
        assert "generated_at" in data
        assert data["summary"]["total_species"] == 42

        # Verify mock was called correctly
        client.mock_presentation_manager.get_analysis_page_data.assert_called_once_with(
            start_date="2025-01-01", end_date="2025-01-15", comparison_period=None
        )

    def test_get_analysis_data_defaults_to_30_days(self, client):
        """Should default to last 30 days when dates not provided."""
        # Setup mock data
        mock_data = {
            "analyses": {},
            "summary": {},
            "generated_at": datetime.now().isoformat(),
        }

        # Don't re-spec methods on an already spec'd mock - just configure return values
        client.mock_presentation_manager.get_analysis_page_data.return_value = mock_data

        # Make request without dates
        response = client.get("/api/analysis")

        # Verify response
        assert response.status_code == 200

        # Verify mock was called with date parameters (exact dates will vary)
        call_args = client.mock_presentation_manager.get_analysis_page_data.call_args
        assert call_args is not None
        assert "start_date" in call_args.kwargs
        assert "end_date" in call_args.kwargs
        assert call_args.kwargs["comparison_period"] is None

    def test_get_analysis_data_with_comparison(self, client):
        """Should pass comparison period to presentation manager."""
        # Setup mock data
        mock_data = {
            "analyses": {},
            "summary": {},
            "generated_at": datetime.now().isoformat(),
        }

        # Don't re-spec methods on an already spec'd mock - just configure return values
        client.mock_presentation_manager.get_analysis_page_data.return_value = mock_data

        # Make request with comparison
        response = client.get(
            "/api/analysis?start_date=2025-01-01&end_date=2025-01-15&comparison=previous"
        )

        # Verify response
        assert response.status_code == 200

        # Verify comparison was passed correctly
        client.mock_presentation_manager.get_analysis_page_data.assert_called_once_with(
            start_date="2025-01-01", end_date="2025-01-15", comparison_period="previous"
        )

    def test_get_analysis_data_error_handling(self, client):
        """Should return 500 status on errors."""
        # Configure mock to raise exception
        client.mock_presentation_manager.get_analysis_page_data.side_effect = Exception(
            "Database error"
        )

        # Make request
        response = client.get("/api/analysis?start_date=2025-01-01&end_date=2025-01-15")

        # Verify error response
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Database error" in data["detail"]
