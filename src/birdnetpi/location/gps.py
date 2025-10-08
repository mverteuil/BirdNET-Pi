"""GPS service for real-time location tracking in field deployments.

This service provides GPS coordinate tracking for mobile BirdNET-Pi deployments,
supporting both real-time location updates and retroactive location tagging.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from gpsdclient.client import GPSDClient

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

        # Initialize GPS client
        self.gpsd_client: GPSDClient | None = None
        if enable_gps:
            try:
                self.gpsd_client = GPSDClient()
                logger.info("GPS support enabled with gpsdclient")
            except Exception as e:
                logger.warning("Failed to initialize GPS client: %s", e)
                self.enable_gps = False

    async def start(self) -> None:
        """Start GPS tracking service."""
        if not self.enable_gps or self.is_running:
            return

        logger.info("Starting GPS service...")
        self.is_running = True

        # gpsdclient connects automatically when streaming data
        # No explicit connect() call needed

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
            # Get GPS fix from gpsdclient - get one packet from the stream
            for packet in self.gpsd_client.dict_stream(filter={"TPV"}):
                # TPV (Time-Position-Velocity) packets contain position data
                mode = packet.get("mode", 0)

                # Check if we have a valid fix
                if mode < 2:  # No fix or invalid fix
                    logger.debug("No GPS fix available (mode: %d)", mode)
                    return

                # Extract coordinates
                coordinates = GPSCoordinates(
                    latitude=packet.get("lat", 0.0),
                    longitude=packet.get("lon", 0.0),
                    altitude=packet.get("alt"),
                    accuracy=packet.get("eps"),
                    timestamp=datetime.now(UTC),
                    satellite_count=packet.get("nSat"),
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

                # Only process one packet per update
                break

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
            age = (datetime.now(UTC) - self.current_location.timestamp).total_seconds()
            if age <= self.update_interval * 2:
                return self.current_location

        return None

    def get_last_known_location(self) -> GPSCoordinates | None:
        """Get last known GPS coordinates (may be stale).

        Returns:
            Last known GPS coordinates or None if never obtained
        """
        return self.last_known_location

    def get_location_at_time(
        self, target_time: datetime, tolerance_seconds: float = 30.0
    ) -> GPSCoordinates | None:
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

        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)
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
