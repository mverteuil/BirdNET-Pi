"""Integration tests for reports view routes."""

from unittest.mock import AsyncMock, MagicMock

from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.web.core.container import Container


class TestReportsViewRoutes:
    """Test reports view routes render without errors."""

    def test_detections_page(self, app_with_temp_data):
        """Should detections page renders with mocked presentation manager."""
        # Mock the presentation manager to avoid database queries
        mock_presentation_manager = MagicMock(spec=PresentationManager)
        mock_presentation_manager.get_detection_display_data = AsyncMock(
            return_value={
                "location": "0.0, 0.0",
                "current_date": "2024-01-01",
                "species_count": 0,
                "recent_detections": [],
                "species_frequency": [],
                "top_species": [],
                "weekly_patterns": [],
                "sparkline_data": {},
                "week_patterns_data": {},
                "heatmap_data": [],
                "stem_leaf_data": [],
            }
        )

        Container.presentation_manager.override(
            providers.Singleton(lambda: mock_presentation_manager)
        )

        try:
            with TestClient(app_with_temp_data) as client:
                response = client.get("/detections")
                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]
        finally:
            Container.presentation_manager.reset_override()

    def test_analysis_page(self, app_with_temp_data):
        """Should analysis page renders with mocked presentation manager."""
        mock_presentation_manager = MagicMock(spec=PresentationManager)
        mock_presentation_manager.get_analysis_page_data = AsyncMock(
            return_value={"analyses": {}, "summary": {}}
        )

        Container.presentation_manager.override(
            providers.Singleton(lambda: mock_presentation_manager)
        )

        try:
            with TestClient(app_with_temp_data) as client:
                response = client.get("/reports/analysis")
                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]
        finally:
            Container.presentation_manager.reset_override()

    def test_best_recordings_page(self, app_with_temp_data):
        """Should best recordings page renders with mocked query service."""
        mock_detection_query_service = MagicMock(spec=DetectionQueryService)
        mock_detection_query_service.query_detections = AsyncMock(return_value=[])

        Container.detection_query_service.override(
            providers.Singleton(lambda: mock_detection_query_service)
        )

        try:
            with TestClient(app_with_temp_data) as client:
                response = client.get("/reports/best")
                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]
        finally:
            Container.detection_query_service.reset_override()
