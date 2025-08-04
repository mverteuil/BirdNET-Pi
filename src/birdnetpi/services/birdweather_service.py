from birdnetpi.models.config import BirdNETConfig


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
            print(f"Successfully sent detection to BirdWeather: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send detection to BirdWeather: {e}")

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
            print(f"Successfully retrieved BirdWeather data: {response.status_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve BirdWeather data: {e}")
            return {}
