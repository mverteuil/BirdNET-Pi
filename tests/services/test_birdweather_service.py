from unittest.mock import MagicMock, patch

import pytest
import requests

from birdnetpi.services.birdweather_service import BirdWeatherService


@pytest.fixture
def birdweather_service():
    """Return a BirdWeatherService instance."""
    return BirdWeatherService()


def test_send_detection_to_birdweather_success(birdweather_service):
    """Should successfully send detection data to BirdWeather API."""
    detection_data = {"species": "Test Bird", "confidence": 0.9}
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        birdweather_service.send_detection_to_birdweather(detection_data)
        mock_post.assert_called_once_with(
            "https://api.birdweather.com/detections", json=detection_data, timeout=5
        )


def test_send_detection_to_birdweather_failure(birdweather_service):
    """Should handle failure when sending detection data to BirdWeather API."""
    detection_data = {"species": "Test Bird", "confidence": 0.9}
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.RequestException("Test Error")

        birdweather_service.send_detection_to_birdweather(detection_data)
        mock_post.assert_called_once_with(
            "https://api.birdweather.com/detections", json=detection_data, timeout=5
        )
