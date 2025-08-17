from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.notifications.birdweather_service import BirdWeatherService


@pytest.fixture
def birdweather_service():
    """Return a BirdWeatherService instance."""
    mock_config = MagicMock()
    mock_config.birdweather_id = "mock_api_key"
    service = BirdWeatherService(config=mock_config)
    return service


def test_send_detection_to_birdweather(birdweather_service):
    """Should successfully send detection data to BirdWeather API."""
    detection_data = {"species": "Test Bird", "confidence": 0.9}
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        birdweather_service.send_detection_to_birdweather(detection_data)
        mock_post.assert_called_once_with(
            "https://api.birdweather.com/detections",
            json=detection_data,
            headers={"X-API-Key": "mock_api_key"},
            timeout=5,
        )


def test_send_detection_to_birdweather_failure(birdweather_service):
    """Should handle failure when sending detection data to BirdWeather API."""
    detection_data = {"species": "Test Bird", "confidence": 0.9}
    with patch("requests.post") as mock_post:
        # Create a real RequestException to test the exception handling
        import requests.exceptions

        mock_post.side_effect = requests.exceptions.RequestException("Test Error")

        birdweather_service.send_detection_to_birdweather(detection_data)
        mock_post.assert_called_once_with(
            "https://api.birdweather.com/detections",
            json=detection_data,
            headers={"X-API-Key": "mock_api_key"},
            timeout=5,
        )


def test_get_birdweather_data(birdweather_service):
    """Should successfully retrieve BirdWeather data."""
    location_data = {"lat": 12.34, "lon": 56.78}
    expected_data = {"weather": "sunny"}
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_data
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = birdweather_service.get_birdweather_data(location_data)
        assert result == expected_data
        mock_get.assert_called_once_with(
            "https://api.birdweather.com/data",
            params=location_data,
            headers={"X-API-Key": "mock_api_key"},
            timeout=5,
        )


def test_get_birdweather_data_failure(birdweather_service):
    """Should handle failure when retrieving BirdWeather data."""
    location_data = {"lat": 12.34, "lon": 56.78}
    with patch("requests.get") as mock_get:
        # Create a real RequestException to test the exception handling
        import requests.exceptions

        mock_get.side_effect = requests.exceptions.RequestException("Test Error")

        result = birdweather_service.get_birdweather_data(location_data)
        assert result == {}
        mock_get.assert_called_once_with(
            "https://api.birdweather.com/data",
            params=location_data,
            headers={"X-API-Key": "mock_api_key"},
            timeout=5,
        )
