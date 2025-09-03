from datetime import date, datetime

from astral import LocationInfo
from astral.sun import sun


class SunService:
    """Provides sun-related services, such as sunrise and sunset times."""

    def __init__(self, latitude: float, longitude: float) -> None:
        self.location = LocationInfo(
            latitude=latitude, longitude=longitude, timezone="UTC", name=""
        )

    def get_sunrise_sunset_times(self, target_date: date) -> tuple[datetime, datetime]:
        """Calculate sunrise and sunset times for a given date and location using astral."""
        s = sun(self.location.observer, date=target_date, tzinfo=self.location.timezone)
        return s["sunrise"], s["sunset"]
