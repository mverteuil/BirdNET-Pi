import pytest

from birdnetpi.services.birdweather_service import BirdWeatherService


@pytest.fixture
def birdweather_service() -> BirdWeatherService:
    """Provide a BirdWeatherService instance for testing."""
    return BirdWeatherService()


def test_send_detection_to_birdweather(birdweather_service, capsys):
    """Should print a message indicating detection data is being sent"""
    detection_data = {"species": "Test Bird", "confidence": 0.99}
    birdweather_service.send_detection_to_birdweather(detection_data)
    captured = capsys.readouterr()
    assert f"Sending detection to BirdWeather: {detection_data}" in captured.out


def test_get_birdweather_data(birdweather_service, capsys):
    """Should print a message and return an empty dictionary for BirdWeather data"""
    location_data = {"latitude": 0.0, "longitude": 0.0}
    results = birdweather_service.get_birdweather_data(location_data)
    captured = capsys.readouterr()
    assert f"Getting BirdWeather data for location: {location_data}" in captured.out
    assert results == {}
