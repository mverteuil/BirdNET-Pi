from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Import from new router structure after refactor
from birdnetpi.web.routers.detection_api_routes import router as detection_router
from birdnetpi.web.routers.system_api_routes import router as system_router  
from birdnetpi.web.routers.field_api_routes import router as field_router
from birdnetpi.web.routers.iot_api_routes import router as iot_router


@pytest.fixture
def mock_app():
    """Create a FastAPI app with mocked app state."""
    app = FastAPI()

    # Set up app state with mocks
    app.state.detections = MagicMock()
    app.state.gps_service = MagicMock()
    app.state.hardware_monitor = MagicMock()
    app.state.mqtt_service = MagicMock()
    app.state.webhook_service = MagicMock()
    app.state.file_manager = MagicMock()
    app.state.file_manager.file_path_resolver.get_birdnetpi_config_path.return_value = (
        "/test/config.yaml"
    )

    # Include all the routers that were split from the original api_router
    app.include_router(detection_router, prefix="/api/detections")
    app.include_router(system_router, prefix="/api/system")
    app.include_router(field_router, prefix="/api/field")
    app.include_router(iot_router, prefix="/api/iot")
    return app


@pytest.fixture
def client(mock_app):
    """Create a test client."""
    return TestClient(mock_app)


class TestDependencyInjection:
    """Test dependency injection functions."""

    def test_get_detection_manager(self):
        """Should return detection manager from app state."""
        request = MagicMock(spec=Request)
        request.app.state.detections = "mock_detection_manager"
        result = get_detection_manager(request)
        assert result == "mock_detection_manager"

    def test_get_gps_service(self):
        """Should return GPS service from app state."""
        request = MagicMock(spec=Request)
        request.app.state.gps_service = "mock_gps_service"
        result = get_gps_service(request)
        assert result == "mock_gps_service"

    def test_get_hardware_monitor(self):
        """Should return hardware monitor from app state."""
        request = MagicMock(spec=Request)
        request.app.state.hardware_monitor = "mock_hardware_monitor"
        result = get_hardware_monitor(request)
        assert result == "mock_hardware_monitor"

    def test_get_mqtt_service(self):
        """Should return MQTT service from app state."""
        request = MagicMock(spec=Request)
        request.app.state.mqtt_service = "mock_mqtt_service"
        result = get_mqtt_service(request)
        assert result == "mock_mqtt_service"

    def test_get_webhook_service(self):
        """Should return webhook service from app state."""
        request = MagicMock(spec=Request)
        request.app.state.webhook_service = "mock_webhook_service"
        result = get_webhook_service(request)
        assert result == "mock_webhook_service"


class TestDetectionEndpoints:
    """Test detection-related API endpoints."""

    def test_get_detections_success(self, client):
        """Should return detections with count."""
        mock_detections = [{"id": 1, "species": "Robin"}, {"id": 2, "species": "Sparrow"}]
        client.app.state.detections.get_recent_detections.return_value = mock_detections

        response = client.get("/api/detections?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["detections"] == mock_detections
        assert data["count"] == 2

    def test_get_detections_default_params(self, client):
        """Should use default limit and offset parameters."""
        client.app.state.detections.get_recent_detections.return_value = []

        response = client.get("/api/detections")

        assert response.status_code == 200
        client.app.state.detections.get_recent_detections.assert_called_once_with(limit=100)


class TestGPSEndpoints:
    """Test GPS-related API endpoints."""

    def test_get_gps_status_enabled(self, client):
        """Should return GPS status when enabled."""
        client.app.state.gps_service.enable_gps = True
        client.app.state.gps_service.update_interval = 5.0
        client.app.state.gps_service._gps_task = MagicMock()

        response = client.get("/api/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["active"] is True
        assert data["update_interval"] == 5.0

    def test_get_gps_status_disabled(self, client):
        """Should return GPS status when disabled."""
        client.app.state.gps_service.enable_gps = False
        client.app.state.gps_service.update_interval = 5.0

        response = client.get("/api/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["active"] is False

    def test_get_gps_location_success(self, client):
        """Should return current GPS location when enabled."""
        client.app.state.gps_service.enable_gps = True
        mock_location = {"latitude": 40.7128, "longitude": -74.0060}
        client.app.state.gps_service.get_current_location.return_value = mock_location

        response = client.get("/api/gps/location")

        assert response.status_code == 200
        data = response.json()
        assert data["location"] == mock_location

    def test_get_gps_location_disabled(self, client):
        """Should return 404 when GPS is disabled."""
        client.app.state.gps_service.enable_gps = False

        response = client.get("/api/gps/location")

        assert response.status_code == 404
        assert "GPS service is not enabled" in response.json()["detail"]


class TestHardwareEndpoints:
    """Test hardware monitoring API endpoints."""

    def test_get_hardware_status(self, client):
        """Should return system hardware status."""
        mock_status = {"cpu": "healthy", "memory": "normal", "temperature": 45.2}
        client.app.state.hardware_monitor.get_all_status.return_value = mock_status

        response = client.get("/api/hardware/status")

        assert response.status_code == 200
        assert response.json() == mock_status

    def test_get_hardware_component_success(self, client):
        """Should return specific component status."""
        mock_status = {"status": "healthy", "value": 45.2}
        client.app.state.hardware_monitor.get_component_status.return_value = mock_status

        response = client.get("/api/hardware/component/cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "cpu"
        assert data["status"] == mock_status

    def test_get_hardware_component_not_found(self, client):
        """Should return 404 for unknown component."""
        client.app.state.hardware_monitor.get_component_status.return_value = None

        response = client.get("/api/hardware/component/unknown")

        assert response.status_code == 404
        assert "Component 'unknown' not found" in response.json()["detail"]


class TestFieldModeEndpoints:
    """Test field mode API endpoints."""

    def test_get_field_summary(self, client):
        """Should return comprehensive field summary."""
        # Setup GPS service
        client.app.state.gps_service.enable_gps = True
        mock_location = {"latitude": 40.7128, "longitude": -74.0060}
        client.app.state.gps_service.get_current_location.return_value = mock_location

        # Setup hardware monitor
        mock_hw_status = {"cpu": "healthy"}
        client.app.state.hardware_monitor.get_all_status.return_value = mock_hw_status

        # Setup detection manager
        mock_recent_detections = [{"id": 1}]
        client.app.state.detections.get_recent_detections.return_value = mock_recent_detections

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
        client.app.state.mqtt_service.enable_mqtt = True
        client.app.state.mqtt_service.publish_message = AsyncMock()

        # Setup webhook service
        client.app.state.webhook_service.enable_webhooks = True
        client.app.state.webhook_service.send_webhook = AsyncMock()

        alert_data = {"alert_type": "battery_low", "severity": "warning"}

        response = client.post("/api/field/alert", json=alert_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alert_sent"
        assert data["data"] == alert_data


class TestIoTEndpoints:
    """Test IoT integration API endpoints."""

    def test_get_mqtt_status_enabled(self, client):
        """Should return MQTT status when enabled."""
        client.app.state.mqtt_service.enable_mqtt = True
        client.app.state.mqtt_service.is_connected = True
        client.app.state.mqtt_service.broker_host = "localhost"
        client.app.state.mqtt_service.broker_port = 1883

        response = client.get("/api/iot/mqtt/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["connected"] is True
        assert data["broker_host"] == "localhost"
        assert data["broker_port"] == 1883

    def test_get_mqtt_status_disabled(self, client):
        """Should return MQTT status when disabled."""
        client.app.state.mqtt_service.enable_mqtt = False

        response = client.get("/api/iot/mqtt/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["connected"] is False
        assert data["broker_host"] is None
        assert data["broker_port"] is None

    def test_get_webhook_status_enabled(self, client):
        """Should return webhook status when enabled."""
        client.app.state.webhook_service.enable_webhooks = True
        client.app.state.webhook_service.webhooks = [
            "http://example.com/webhook1",
            "http://example.com/webhook2",
        ]

        response = client.get("/api/iot/webhooks/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["configured_urls"] == 2

    def test_get_webhook_status_disabled(self, client):
        """Should return webhook status when disabled."""
        client.app.state.webhook_service.enable_webhooks = False

        response = client.get("/api/iot/webhooks/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["configured_urls"] == 0

    def test_test_iot_services(self, client):
        """Should test IoT service connectivity."""
        # Setup MQTT service
        client.app.state.mqtt_service.enable_mqtt = True
        client.app.state.mqtt_service.is_connected = True

        # Setup webhook service
        client.app.state.webhook_service.enable_webhooks = True
        client.app.state.webhook_service.webhooks = ["http://example.com/webhook"]

        response = client.post("/api/iot/test")

        assert response.status_code == 200
        data = response.json()
        assert data["test_results"]["mqtt"] is True
        assert data["test_results"]["webhooks"] is True


class TestConfigurationEndpoints:
    """Test configuration API endpoints."""

    def test_validate_yaml_config_invalid_yaml(self, client):
        """Should return error for invalid YAML syntax."""
        invalid_yaml = """
site_name: "Test Site
latitude: [invalid
"""

        response = client.post("/api/config/validate", json={"yaml_content": invalid_yaml})

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "YAML syntax error" in data["error"]
