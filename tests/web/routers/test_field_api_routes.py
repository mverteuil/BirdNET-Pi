"""Tests for field API routes that handle field mode functionality and GPS integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.services.mqtt_service import MQTTService
from birdnetpi.services.webhook_service import WebhookService
from birdnetpi.web.routers.field_api_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""

    detection_manager = providers.Singleton(MagicMock, spec=DetectionManager)
    gps_service = providers.Singleton(MagicMock, spec=GPSService)
    hardware_monitor_service = providers.Singleton(MagicMock, spec=HardwareMonitorService)
    mqtt_service = providers.Singleton(MagicMock, spec=MQTTService)
    webhook_service = providers.Singleton(MagicMock, spec=WebhookService)


@pytest.fixture
def app_with_field_router():
    """Create FastAPI app with field router and DI container."""
    app = FastAPI()

    # Setup test container
    container = TestContainer()
    app.container = container

    # Wire the router module
    container.wire(modules=["birdnetpi.web.routers.field_api_routes"])

    # Include the router
    app.include_router(router, prefix="/api/field")

    return app


@pytest.fixture
def client(app_with_field_router):
    """Create test client."""
    return TestClient(app_with_field_router)


class TestGPSEndpoints:
    """Test GPS-related API endpoints."""

    def test_get_gps_status_enabled(self, client):
        """Should return GPS status when enabled."""
        gps_service = client.app.container.gps_service()
        gps_service.enable_gps = True
        gps_service.update_interval = 5.0
        gps_service._gps_task = MagicMock()

        response = client.get("/api/field/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["active"] is True
        assert data["update_interval"] == 5.0

    def test_get_gps_status_disabled(self, client):
        """Should return GPS status when disabled."""
        gps_service = client.app.container.gps_service()
        gps_service.enable_gps = False
        gps_service.update_interval = 5.0

        response = client.get("/api/field/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["active"] is False

    def test_get_gps_location_success(self, client):
        """Should return current GPS location when enabled."""
        gps_service = client.app.container.gps_service()
        gps_service.enable_gps = True
        mock_location = {"latitude": 40.7128, "longitude": -74.0060}
        gps_service.get_current_location.return_value = mock_location

        response = client.get("/api/field/gps/location")

        assert response.status_code == 200
        data = response.json()
        assert data["location"] == mock_location

    def test_get_gps_location_disabled(self, client):
        """Should return 404 when GPS is disabled."""
        gps_service = client.app.container.gps_service()
        gps_service.enable_gps = False

        response = client.get("/api/field/gps/location")

        assert response.status_code == 404
        assert "GPS service is not enabled" in response.json()["detail"]


class TestFieldModeEndpoints:
    """Test field mode API endpoints."""

    def test_get_field_summary(self, client):
        """Should return comprehensive field summary."""
        # Setup GPS service
        gps_service = client.app.container.gps_service()
        gps_service.enable_gps = True
        mock_location = {"latitude": 40.7128, "longitude": -74.0060}
        gps_service.get_current_location.return_value = mock_location

        # Setup hardware monitor
        hardware_monitor = client.app.container.hardware_monitor_service()
        mock_hw_status = {"cpu": "healthy"}
        hardware_monitor.get_all_status.return_value = mock_hw_status

        # Setup detection manager
        detection_manager = client.app.container.detection_manager()
        mock_recent_detections = [{"id": 1}]
        detection_manager.get_recent_detections.return_value = mock_recent_detections

        response = client.get("/api/field/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["gps"]["enabled"] is True
        assert data["gps"]["location"] == mock_location
        assert data["hardware"] == mock_hw_status
        assert data["detections"]["today_count"] == 0  # TODO is hardcoded to 0 in implementation
        assert data["detections"]["recent"] == mock_recent_detections

    def test_create_field_alert(self, client):
        """Should create and send field alert."""
        # Setup MQTT service
        mqtt_service = client.app.container.mqtt_service()
        mqtt_service.enable_mqtt = True
        mqtt_service.publish_message = AsyncMock()

        # Setup webhook service
        webhook_service = client.app.container.webhook_service()
        webhook_service.enable_webhooks = True
        webhook_service.send_webhook = AsyncMock()

        alert_data = {"alert_type": "battery_low", "severity": "warning"}

        response = client.post("/api/field/alert", json=alert_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alert_sent"
        assert data["data"] == alert_data
