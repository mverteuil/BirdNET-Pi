"""GPS service for real-time location tracking in field deployments.

This service provides GPS coordinate tracking for mobile BirdNET-Pi deployments,
supporting both real-time location updates and retroactive location tagging.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class GPSCoordinates(NamedTuple):
    """GPS coordinates with timestamp and accuracy information."""

    latitude: float
    longitude: float
    altitude: float | None
    accuracy: float | None
    timestamp: datetime
    satellite_count: int | None = None


class GPSService:
    """Provides GPS location services for field deployments."""

    def __init__(self, enable_gps: bool = False, update_interval: float = 5.0) -> None:
        """Initialize GPS service.

        Args:
            enable_gps: Whether to enable GPS tracking
            update_interval: Time between GPS updates in seconds
        """
        self.enable_gps = enable_gps
        self.update_interval = update_interval
        self.current_location: GPSCoordinates | None = None
        self.last_known_location: GPSCoordinates | None = None
        self.is_running = False
        self.location_history: list[GPSCoordinates] = []
        self._update_task: asyncio.Task[None] | None = None

        # Try to import GPS library
        self.gpsd_client = None
        if enable_gps:
            try:
                import gpsd  # type: ignore[import-untyped]

                self.gpsd_client = gpsd
                logger.info("GPS support enabled with gpsd")
            except ImportError:
                logger.warning(
                    "GPS enabled but gpsd-py3 not installed. "
                    "Install with: pip install gpsd-py3"
                )
                self.enable_gps = False

    async def start(self) -> None:
        """Start GPS tracking service."""
        if not self.enable_gps or self.is_running:
            return

        logger.info("Starting GPS service...")
        self.is_running = True

        # Connect to GPS daemon
        if self.gpsd_client:
            try:
                self.gpsd_client.connect()
                logger.info("Connected to GPS daemon")
            except Exception as e:
                logger.error("Failed to connect to GPS daemon: %s", e)
                self.enable_gps = False
                return

        # Start background update task
        self._update_task = asyncio.create_task(self._update_location_loop())

    async def stop(self) -> None:
        """Stop GPS tracking service."""
        if not self.is_running:
            return

        logger.info("Stopping GPS service...")
        self.is_running = False

        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

    async def _update_location_loop(self) -> None:
        """Background task to update GPS location periodically."""
        while self.is_running:
            try:
                await self._update_location()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in GPS update loop: %s", e)
                await asyncio.sleep(self.update_interval)

    async def _update_location(self) -> None:
        """Update current GPS location."""
        if not self.gpsd_client:
            return

        try:
            # Get GPS fix from gpsd
            packet = self.gpsd_client.get_current()

            # Check if we have a valid fix
            if packet.mode < 2:  # No fix or invalid fix
                logger.debug("No GPS fix available (mode: %d)", packet.mode)
                return

            # Extract coordinates
            coordinates = GPSCoordinates(
                latitude=packet.lat,
                longitude=packet.lon,
                altitude=getattr(packet, "alt", None),
                accuracy=getattr(packet, "eps", None),
                timestamp=datetime.now(timezone.utc),
                satellite_count=getattr(packet, "sats", None),
            )

            # Update current location
            self.current_location = coordinates
            self.last_known_location = coordinates

            # Add to history (keep last 100 locations)
            self.location_history.append(coordinates)
            if len(self.location_history) > 100:
                self.location_history.pop(0)

            logger.debug(
                "GPS updated: %.6f, %.6f (accuracy: %.1fm, satellites: %d)",
                coordinates.latitude,
                coordinates.longitude,
                coordinates.accuracy or 0,
                coordinates.satellite_count or 0,
            )

        except Exception as e:
            logger.error("Error updating GPS location: %s", e)

    def get_current_location(self) -> GPSCoordinates | None:
        """Get current GPS coordinates.

        Returns:
            Current GPS coordinates or None if unavailable
        """
        if not self.enable_gps:
            return None

        # Return current location if recent (within 2x update interval)
        if self.current_location:
            age = (datetime.now(timezone.utc) - self.current_location.timestamp).total_seconds()
            if age <= self.update_interval * 2:
                return self.current_location

        return None

    def get_last_known_location(self) -> GPSCoordinates | None:
        """Get last known GPS coordinates (may be stale).

        Returns:
            Last known GPS coordinates or None if never obtained
        """
        return self.last_known_location

    def get_location_at_time(self, target_time: datetime, tolerance_seconds: float = 30.0) -> GPSCoordinates | None:
        """Get GPS coordinates closest to a specific time.

        Args:
            target_time: Target timestamp to find location for
            tolerance_seconds: Maximum time difference to accept

        Returns:
            GPS coordinates closest to target time within tolerance
        """
        if not self.location_history:
            return None

        closest_location = None
        min_time_diff = float("inf")

        for location in self.location_history:
            time_diff = abs((location.timestamp - target_time).total_seconds())
            if time_diff <= tolerance_seconds and time_diff < min_time_diff:
                min_time_diff = time_diff
                closest_location = location

        return closest_location

    def get_location_history(self, hours: int = 24) -> list[GPSCoordinates]:
        """Get location history for the specified number of hours.

        Args:
            hours: Number of hours of history to return

        Returns:
            List of GPS coordinates within the time range
        """
        if not self.location_history:
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [loc for loc in self.location_history if loc.timestamp >= cutoff_time]

    def is_gps_available(self) -> bool:
        """Check if GPS is enabled and working.

        Returns:
            True if GPS is available and working
        """
        return self.enable_gps and self.current_location is not None

    def get_gps_status(self) -> dict[str, Any]:
        """Get comprehensive GPS status information.

        Returns:
            Dictionary with GPS status details
        """
        status = {
            "enabled": self.enable_gps,
            "running": self.is_running,
            "has_fix": self.current_location is not None,
            "last_update": None,
            "accuracy": None,
            "satellite_count": None,
            "location_history_count": len(self.location_history),
        }

        if self.current_location:
            status.update(
                {
                    "last_update": self.current_location.timestamp.isoformat(),
                    "accuracy": self.current_location.accuracy,
                    "satellite_count": self.current_location.satellite_count,
                    "coordinates": {
                        "latitude": self.current_location.latitude,
                        "longitude": self.current_location.longitude,
                        "altitude": self.current_location.altitude,
                    },
                }
            )

        return status