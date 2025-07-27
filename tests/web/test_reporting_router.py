from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from birdnetpi.web.main import app

client = TestClient(app)


def test_get_best_recordings():
    """Should retrieve the best recordings successfully."""
    # Mock the ReportingManager and its get_best_detections method
    mock_reporting_manager = MagicMock()
    mock_reporting_manager.get_best_detections.return_value = [
        {
            "Date": "2025-07-26",
            "Time": "10:00:00",
            "Sci_Name": "Cardinalis cardinalis",
            "Com_Name": "Northern Cardinal",
            "Confidence": 0.9,
            "Lat": 38.8951,
            "Lon": -77.0364,
        }
    ]

    # Use patch to replace the get_reporting_manager dependency
    with patch(
        "birdnetpi.web.routers.reporting_router.get_reporting_manager",
        return_value=mock_reporting_manager,
    ):
        response = client.get("/best_recordings")

    # Assert the response
    assert response.status_code == 200
    assert "best_recordings" in response.json()
    assert len(response.json()["best_recordings"]) == 1
    assert response.json()["best_recordings"][0]["Com_Name"] == "Northern Cardinal"
