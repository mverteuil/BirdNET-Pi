import logging

from birdnetpi.config import BirdNETConfig

logger = logging.getLogger(__name__)


class BirdWeatherService:
    """Manages interactions with the BirdWeather API."""

    def __init__(self, config: BirdNETConfig) -> None:
        self.config = config

    def send_detection_to_birdweather(self, detection_data: dict) -> None:
        """Send detection data to the BirdWeather API."""
        import requests

        birdweather_api_key = self.config.birdweather_id
        headers = {"X-API-Key": birdweather_api_key}
        try:
            response = requests.post(
                "https://api.birdweather.com/detections",
                json=detection_data,
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
            logger.info(
                "Successfully sent detection to BirdWeather",
                extra={"status_code": response.status_code},
            )
        except requests.exceptions.RequestException as e:
            logger.error("Failed to send detection to BirdWeather", extra={"error": str(e)})

    def get_birdweather_data(self, location: dict) -> dict:
        """Retrieve BirdWeather data for a given location."""
        import requests

        birdweather_api_key = self.config.birdweather_id
        headers = {"X-API-Key": birdweather_api_key}
        try:
            response = requests.get(
                "https://api.birdweather.com/data",
                params=location,
                headers=headers,
                timeout=5,
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
            logger.info(
                "Successfully retrieved BirdWeather data",
                extra={"status_code": response.status_code},
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to retrieve BirdWeather data", extra={"error": str(e)})
            return {}
