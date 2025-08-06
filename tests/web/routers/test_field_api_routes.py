"""Tests for field API routes that handle field mode functionality and GPS integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.field_api_routes import router


@pytest.fixture
def client():
    """Create test client with field API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override services with mocks
    mock_detection_manager = MagicMock(spec=DetectionManager)
    mock_gps_service = MagicMock(spec=GPSService)
    mock_hardware_monitor_service = MagicMock(spec=HardwareMonitorService)
    mock_mqtt_service = MagicMock(spec=MQTTService)
    mock_webhook_service = MagicMock(spec=WebhookService)

    container.detection_manager.override(mock_detection_manager)
    container.gps_service.override(mock_gps_service)
    container.hardware_monitor_service.override(mock_hardware_monitor_service)
    container.mqtt_service.override(mock_mqtt_service)
    container.webhook_service.override(mock_webhook_service)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.field_api_routes"])
    app.container = container

    # Include the router
    app.include_router(router, prefix="/api/field")

    # Create and return test client
    client = TestClient(app)

    # Store the mocks for access in tests
    client.mock_detection_manager = mock_detection_manager
    client.mock_gps_service = mock_gps_service
    client.mock_hardware_monitor_service = mock_hardware_monitor_service
    client.mock_mqtt_service = mock_mqtt_service
    client.mock_webhook_service = mock_webhook_service

    return client


class TestGPSEndpoints:
    """Test GPS-related API endpoints."""

    def test_get_gps_status_enabled(self, client):
        """Should return GPS status when enabled."""
        gps_service = client.mock_gps_service
        mock_status = {"enabled": True, "available": True, "active": True, "update_interval": 5.0}
        gps_service.get_gps_status.return_value = mock_status

        response = client.get("/api/field/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["active"] is True
        assert data["update_interval"] == 5.0

    def test_get_gps_status_disabled(self, client):
        """Should return GPS status when disabled."""
        gps_service = client.mock_gps_service
        mock_status = {"enabled": False, "available": False, "active": False}
        gps_service.get_gps_status.return_value = mock_status

        response = client.get("/api/field/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["active"] is False

    def test_get_gps_location_success(self, client):
        """Should return current GPS location when enabled."""
        gps_service = client.mock_gps_service
        mock_location = MagicMock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060
        mock_location.altitude = 100.0
        mock_location.accuracy = 5.0
        mock_location.timestamp.isoformat.return_value = "2025-01-15T10:30:00"
        mock_location.satellite_count = 8
        gps_service.get_current_location.return_value = mock_location

        response = client.get("/api/field/gps/location")

        assert response.status_code == 200
        data = response.json()
        assert data["latitude"] == 40.7128
        assert data["longitude"] == -74.0060
        assert data["altitude"] == 100.0
        assert data["accuracy"] == 5.0
        assert data["timestamp"] == "2025-01-15T10:30:00"
        assert data["satellite_count"] == 8

    def test_get_gps_location_disabled(self, client):
        """Should return 404 when GPS service is not available."""
        # Mock get_current_location to return None (GPS disabled)
        client.mock_gps_service.get_current_location.return_value = None

        response = client.get("/api/field/gps/location")

        assert response.status_code == 404
        assert "No GPS fix available" in response.json()["error"]


class TestFieldModeEndpoints:
    """Test field mode API endpoints."""

    def test_get_field_summary(self, client):
        """Should return comprehensive field summary."""
        # Setup GPS service
        gps_service = client.mock_gps_service
        gps_service.get_gps_status.return_value = {"enabled": True}

        # Setup hardware monitor
        hardware_monitor = client.mock_hardware_monitor_service
        hardware_monitor.get_health_summary.return_value = {"overall_status": "healthy"}

        # Setup detection manager
        detection_manager = client.mock_detection_manager
        detection_manager.get_detections_count_by_date.return_value = 5

        # Create mock detection objects with required attributes
        from datetime import UTC, datetime
        from unittest.mock import Mock

        mock_detection = Mock()
        mock_detection.species = "Test Bird"
        mock_detection.confidence = 0.95
        mock_detection.timestamp = datetime.now(UTC)

        detection_manager.get_recent_detections.return_value = [mock_detection]

        response = client.get("/api/field/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["gps"]["enabled"] is True
        assert data["hardware"]["overall_status"] == "healthy"
        assert data["detections"]["today_count"] == 5
        assert len(data["detections"]["recent"]) == 1
        assert data["detections"]["recent"][0]["species"] == "Test Bird"
        assert data["detections"]["recent"][0]["confidence"] == 0.95

    def test_create_field_alert(self, client):
        """Should create and send field alert."""
        # Setup MQTT service
        mqtt_service = client.mock_mqtt_service
        mqtt_service.enable_mqtt = True
        mqtt_service.publish_message = AsyncMock()

        # Setup webhook service
        webhook_service = client.mock_webhook_service
        webhook_service.enable_webhooks = True
        webhook_service.send_webhook = AsyncMock()

        alert_data = {"message": "Battery low", "level": "warning"}

        response = client.post("/api/field/alert", json=alert_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Alert triggered"
        assert data["level"] == "warning"
        assert data["text"] == "Battery low"
