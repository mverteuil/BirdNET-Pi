"""Tests for the GPSService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.location.gps import GPSCoordinates, GPSService


@pytest.fixture
def gps_service():
    """Create a GPSService instance for testing."""
    return GPSService(enable_gps=False, update_interval=1.0)  # Disabled for most tests


@pytest.fixture
def enabled_gps_service():
    """Create an enabled GPSService instance for testing."""
    # Mock the gpsd module at import time
    mock_gpsd = MagicMock()
    with patch.dict("sys.modules", {"gpsd": mock_gpsd}):
        service = GPSService(enable_gps=True, update_interval=1.0)
        return service


class TestGPSService:
    """Test the GPSService class."""

    def test_initialization_disabled(self, gps_service):
        """Test that GPSService initializes correctly when disabled."""
        assert not gps_service.enable_gps
        assert gps_service.update_interval == 1.0
        assert gps_service.current_location is None
        assert gps_service.last_known_location is None
        assert not gps_service.is_running
        assert len(gps_service.location_history) == 0

    def test_initialization_enabled(self):
        """Test GPSService initialization when GPS is enabled."""
        # Mock the gpsd module at import time
        mock_gpsd = MagicMock()
        with patch.dict("sys.modules", {"gpsd": mock_gpsd}):
            service = GPSService(enable_gps=True, update_interval=2.0)
            assert service.enable_gps
            assert service.update_interval == 2.0

    @pytest.mark.asyncio
    async def test_start_stop_disabled(self, gps_service):
        """Test starting and stopping GPS service when disabled."""
        await gps_service.start()
        assert not gps_service.is_running

        await gps_service.stop()
        assert not gps_service.is_running

    @pytest.mark.asyncio
    async def test_start_stop_enabled(self, enabled_gps_service):
        """Test starting and stopping GPS service when enabled."""
        service = enabled_gps_service
        service.gpsd_client.connect = MagicMock()

        await service.start()
        assert service.is_running
        service.gpsd_client.connect.assert_called_once()

        await service.stop()
        assert not service.is_running

    def test_get_current_location_disabled(self, gps_service):
        """Test getting current location when GPS is disabled."""
        location = gps_service.get_current_location()
        assert location is None

    def test_get_current_location__no_fix(self, enabled_gps_service):
        """Test getting current location when no GPS fix is available."""
        service = enabled_gps_service
        location = service.get_current_location()
        assert location is None

    def test_get_current_location__fix(self, enabled_gps_service):
        """Test getting current location with valid GPS fix."""
        service = enabled_gps_service

        # Create a recent location
        now = datetime.now(UTC)
        test_location = GPSCoordinates(
            latitude=63.4591,
            longitude=-19.3647,
            altitude=10.0,
            accuracy=5.0,
            timestamp=now,
            satellite_count=8,
        )
        service.current_location = test_location

        location = service.get_current_location()
        assert location is not None
        assert location.latitude == 63.4591
        assert location.longitude == -19.3647
        assert location.altitude == 10.0
        assert location.accuracy == 5.0
        assert location.satellite_count == 8

    def test_get_last_known_location(self, enabled_gps_service):
        """Test getting last known location."""
        service = enabled_gps_service

        test_location = GPSCoordinates(
            latitude=63.4591,
            longitude=-19.3647,
            altitude=10.0,
            accuracy=5.0,
            timestamp=datetime.now(UTC),
            satellite_count=8,
        )
        service.last_known_location = test_location

        location = service.get_last_known_location()
        assert location is not None
        assert location.latitude == 63.4591
        assert location.longitude == -19.3647

    def test_get_location_at_time(self, enabled_gps_service):
        """Test getting location at a specific time."""
        service = enabled_gps_service

        # Create test locations with different timestamps
        # Use a fixed base time to avoid timing issues
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        locations = [
            GPSCoordinates(40.0, -74.0, 10.0, 5.0, base_time, 8),
            GPSCoordinates(40.1, -74.1, 11.0, 4.0, base_time.replace(second=30), 7),
            GPSCoordinates(40.2, -74.2, 12.0, 3.0, base_time.replace(minute=1), 6),
        ]
        service.location_history = locations

        # Test exact match
        location = service.get_location_at_time(base_time.replace(second=30))
        assert location is not None
        assert location.latitude == 40.1

        # Test closest match within tolerance
        location = service.get_location_at_time(
            base_time.replace(second=25), tolerance_seconds=10.0
        )
        assert location is not None
        assert location.latitude == 40.1

        # Test no match outside tolerance
        location = service.get_location_at_time(base_time.replace(minute=5), tolerance_seconds=10.0)
        assert location is None

    def test_get_location_history(self, enabled_gps_service):
        """Test getting location history."""
        service = enabled_gps_service

        # Create test locations
        now = datetime.now(UTC)
        locations = [
            GPSCoordinates(40.0, -74.0, 10.0, 5.0, now, 8),
            GPSCoordinates(40.1, -74.1, 11.0, 4.0, now, 7),
        ]
        service.location_history = locations

        history = service.get_location_history(hours=24)
        assert len(history) == 2
        assert history[0].latitude == 40.0
        assert history[1].latitude == 40.1

    def test_is_gps_available(self, gps_service, enabled_gps_service):
        """Test GPS availability check."""
        # Disabled service
        assert not gps_service.is_gps_available()

        # Enabled service without fix
        assert not enabled_gps_service.is_gps_available()

        # Enabled service with fix
        enabled_gps_service.current_location = GPSCoordinates(
            40.0, -74.0, 10.0, 5.0, datetime.now(UTC), 8
        )
        assert enabled_gps_service.is_gps_available()

    def test_get_gps_status_disabled(self, gps_service):
        """Test GPS status when disabled."""
        status = gps_service.get_gps_status()
        assert status["enabled"] is False
        assert status["running"] is False
        assert status["has_fix"] is False
        assert status["last_update"] is None

    def test_get_gps_status_enabled__fix(self, enabled_gps_service):
        """Test GPS status when enabled with GPS fix."""
        service = enabled_gps_service
        service.is_running = True

        test_location = GPSCoordinates(
            latitude=63.4591,
            longitude=-19.3647,
            altitude=10.0,
            accuracy=5.0,
            timestamp=datetime.now(UTC),
            satellite_count=8,
        )
        service.current_location = test_location

        status = service.get_gps_status()
        assert status["enabled"] is True
        assert status["running"] is True
        assert status["has_fix"] is True
        assert status["coordinates"]["latitude"] == 63.4591
        assert status["coordinates"]["longitude"] == -19.3647
        assert status["accuracy"] == 5.0
        assert status["satellite_count"] == 8

    @pytest.mark.asyncio
    async def test_update_location__no_client(self, enabled_gps_service):
        """Test location update when no GPSD client is available."""
        service = enabled_gps_service
        service.gpsd_client = None

        await service._update_location()
        # Should not raise an exception and should not update location
        assert service.current_location is None

    @pytest.mark.asyncio
    async def test_update_location__no_fix(self, enabled_gps_service):
        """Test location update when GPS has no fix."""
        service = enabled_gps_service

        # Mock GPS packet with no fix
        mock_packet = MagicMock()
        mock_packet.mode = 1  # No valid fix
        service.gpsd_client.get_current.return_value = mock_packet

        await service._update_location()
        assert service.current_location is None

    @pytest.mark.asyncio
    async def test_update_location__fix(self, enabled_gps_service):
        """Test location update with valid GPS fix."""
        service = enabled_gps_service

        # Mock GPS packet with valid fix
        mock_packet = MagicMock()
        mock_packet.mode = 3  # 3D fix
        mock_packet.lat = 63.4591
        mock_packet.lon = -19.3647
        mock_packet.alt = 10.0
        mock_packet.eps = 5.0
        mock_packet.sats = 8
        service.gpsd_client.get_current.return_value = mock_packet

        await service._update_location()

        assert service.current_location is not None
        assert service.current_location.latitude == 63.4591
        assert service.current_location.longitude == -19.3647
        assert service.current_location.altitude == 10.0
        assert service.current_location.accuracy == 5.0
        assert service.current_location.satellite_count == 8
        assert service.last_known_location is not None

    @pytest.mark.asyncio
    async def test_update_location_history_limit(self, enabled_gps_service):
        """Test that location history is limited to 100 entries."""
        service = enabled_gps_service

        # Fill history with 100 locations
        now = datetime.now(UTC)
        service.location_history = [
            GPSCoordinates(40.0, -74.0, 10.0, 5.0, now, 8) for _ in range(100)
        ]

        # Mock GPS packet with valid fix
        mock_packet = MagicMock()
        mock_packet.mode = 3
        mock_packet.lat = 41.0
        mock_packet.lon = -75.0
        mock_packet.alt = 15.0
        mock_packet.eps = 3.0
        mock_packet.sats = 9
        service.gpsd_client.get_current.return_value = mock_packet

        await service._update_location()

        # History should still be 100 entries, with oldest removed
        assert len(service.location_history) == 100
        assert service.location_history[-1].latitude == 41.0  # New location at end
        assert service.location_history[-1].longitude == -75.0
