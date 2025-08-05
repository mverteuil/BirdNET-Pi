"""Tests for field mode router with dependency injection."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.gps_service import GPSService
from birdnetpi.services.hardware_monitor_service import HardwareMonitorService
from birdnetpi.web.routers.field_mode_router import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""

    # Mock services
    detection_manager = providers.Singleton(MagicMock, spec=DetectionManager)
    gps_service = providers.Singleton(MagicMock, spec=GPSService)
    hardware_monitor_service = providers.Singleton(MagicMock, spec=HardwareMonitorService)
    templates = providers.Singleton(MagicMock)


@pytest.fixture
def test_container():
    """Create test container."""
    container = TestContainer()
    return container


@pytest.fixture
def app_with_container(test_container):
    """Create FastAPI app with test container."""
    app = FastAPI()
    app.container = test_container
    app.include_router(router)
    
    # Wire the router
    test_container.wire(modules=["birdnetpi.web.routers.field_mode_router"])
    
    return app


@pytest.fixture
def client(app_with_container):
    """Create test client."""
    return TestClient(app_with_container)


class TestFieldModeTemplate:
    """Test field mode template endpoint."""

    def test_get_field_mode_template_response(self, client, test_container):
        """Should render field mode template."""
        # Mock the templates
        mock_templates = test_container.templates()
        mock_templates.TemplateResponse.return_value = "mock_template_response"
        
        response = client.get("/field")
        
        assert response.status_code == 200
        mock_templates.TemplateResponse.assert_called_once()


class TestGPSEndpoints:
    """Test GPS-related field mode endpoints."""

    def test_get_gps_status_success(self, client, test_container):
        """Should return GPS status successfully."""
        # Mock GPS service
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_gps_status.return_value = {
            "enabled": True,
            "available": True,
            "latitude": 40.7128,
            "longitude": -74.0060,
        }
        
        response = client.get("/api/gps/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["available"] is True

    def test_get_gps_status_exception(self, client, test_container):
        """Should handle GPS status exceptions."""
        # Mock GPS service to raise exception
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_gps_status.side_effect = Exception("GPS error")
        
        response = client.get("/api/gps/status")
        
        assert response.status_code == 500
        data = response.json()
        assert "GPS error" in data["error"]

    def test_get_current_location_success(self, client, test_container):
        """Should return current GPS location."""
        # Mock GPS service with location data
        mock_gps_service = test_container.gps_service()
        mock_location = MagicMock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060
        mock_location.altitude = 10.0
        mock_location.accuracy = 5.0
        mock_location.timestamp = datetime.now(UTC)
        mock_location.satellite_count = 8
        mock_gps_service.get_current_location.return_value = mock_location
        
        response = client.get("/api/gps/location")
        
        assert response.status_code == 200
        data = response.json()
        assert data["latitude"] == 40.7128
        assert data["longitude"] == -74.0060
        assert data["satellite_count"] == 8

    def test_get_current_location_no_fix(self, client, test_container):
        """Should handle no GPS fix available."""
        # Mock GPS service with no location
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_current_location.return_value = None
        
        response = client.get("/api/gps/location")
        
        assert response.status_code == 404
        data = response.json()
        assert "No GPS fix available" in data["error"]

    def test_get_current_location_exception(self, client, test_container):
        """Should handle GPS location exceptions."""
        # Mock GPS service to raise exception
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_current_location.side_effect = Exception("Location error")
        
        response = client.get("/api/gps/location")
        
        assert response.status_code == 500
        data = response.json()
        assert "Location error" in data["error"]


class TestLocationHistoryEndpoint:
    """Test GPS location history endpoint."""

    def test_get_location_history_success(self, client, test_container):
        """Should return GPS location history."""
        # Mock GPS service with history data
        mock_gps_service = test_container.gps_service()
        mock_locations = [MagicMock() for _ in range(3)]
        for i, loc in enumerate(mock_locations):
            loc.latitude = 40.7128 + i * 0.001
            loc.longitude = -74.0060 + i * 0.001
            loc.altitude = 10.0 + i
            loc.accuracy = 5.0
            loc.timestamp = datetime.now(UTC)
            loc.satellite_count = 8
        mock_gps_service.get_location_history.return_value = mock_locations
        
        response = client.get("/api/gps/history")
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["locations"]) == 3

    def test_get_location_history_with_custom_hours(self, client, test_container):
        """Should accept custom hours parameter."""
        # Mock GPS service
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_location_history.return_value = []
        
        response = client.get("/api/gps/history?hours=48")
        
        assert response.status_code == 200
        # Verify the hours parameter was passed
        mock_gps_service.get_location_history.assert_called_once_with(48)

    def test_get_location_history_service_exception(self, client, test_container):
        """Should handle GPS history exceptions."""
        # Mock GPS service to raise exception
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_location_history.side_effect = Exception("History error")
        
        response = client.get("/api/gps/history")
        
        assert response.status_code == 500
        data = response.json()
        assert "History error" in data["error"]


class TestHardwareEndpoints:
    """Test hardware monitoring endpoints."""

    def test_get_hardware_status_success(self, client, test_container):
        """Should return hardware status."""
        # Mock hardware monitor service
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_hardware_monitor.get_health_summary.return_value = {
            "overall_status": "healthy",
            "components": {"cpu": "ok", "memory": "ok"},
        }
        
        response = client.get("/api/hardware/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert "components" in data

    def test_get_hardware_status_exception(self, client, test_container):
        """Should handle hardware status exceptions."""
        # Mock hardware monitor to raise exception
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_hardware_monitor.get_health_summary.side_effect = Exception("Hardware error")
        
        response = client.get("/api/hardware/status")
        
        assert response.status_code == 500
        data = response.json()
        assert "Hardware error" in data["error"]

    def test_get_component_status_success(self, client, test_container):
        """Should return specific component status."""
        # Mock hardware monitor service
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_component = MagicMock()
        mock_component.name = "cpu"
        mock_component.status.value = "healthy"
        mock_component.message = "CPU is running normally"
        mock_component.last_check = datetime.now(UTC)
        mock_component.details = {"temperature": "45C"}
        mock_hardware_monitor.get_component_status.return_value = mock_component
        
        response = client.get("/api/hardware/component/cpu")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "cpu"
        assert data["status"] == "healthy"
        assert data["message"] == "CPU is running normally"

    def test_get_component_status_not_found(self, client, test_container):
        """Should handle component not found."""
        # Mock hardware monitor to return None
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_hardware_monitor.get_component_status.return_value = None
        
        response = client.get("/api/hardware/component/unknown")
        
        assert response.status_code == 404
        data = response.json()
        assert "Component 'unknown' not found" in data["error"]

    def test_get_component_status_exception(self, client, test_container):
        """Should handle component status exceptions."""
        # Mock hardware monitor to raise exception
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_hardware_monitor.get_component_status.side_effect = Exception("Component error")
        
        response = client.get("/api/hardware/component/cpu")
        
        assert response.status_code == 500
        data = response.json()
        assert "Component error" in data["error"]


class TestFieldSummaryEndpoint:
    """Test field summary endpoint."""

    def test_get_field_summary_success(self, client, test_container):
        """Should return comprehensive field summary."""
        # Mock detection manager
        mock_detection_manager = test_container.detection_manager()
        mock_detection_manager.get_detections_count_by_date.return_value = 15
        mock_detections = [MagicMock() for _ in range(3)]
        for i, detection in enumerate(mock_detections):
            detection.species = f"Bird {i}"
            detection.confidence = 0.8 + i * 0.05
            detection.timestamp = datetime.now(UTC)
        mock_detection_manager.get_recent_detections.return_value = mock_detections
        
        # Mock GPS service
        mock_gps_service = test_container.gps_service()
        mock_gps_service.get_gps_status.return_value = {
            "enabled": True,
            "available": True,
        }
        
        # Mock hardware monitor
        mock_hardware_monitor = test_container.hardware_monitor_service()
        mock_hardware_monitor.get_health_summary.return_value = {
            "overall_status": "healthy",
        }
        
        response = client.get("/api/field/summary")
        
        assert response.status_code == 200
        data = response.json()
        assert data["detections"]["today_count"] == 15
        assert len(data["detections"]["recent"]) == 3
        assert data["gps"]["enabled"] is True
        assert data["hardware"]["overall_status"] == "healthy"

    def test_get_field_summary_exception(self, client, test_container):
        """Should handle field summary exceptions."""
        # Mock detection manager to raise exception
        mock_detection_manager = test_container.detection_manager()
        mock_detection_manager.get_detections_count_by_date.side_effect = Exception("Summary error")
        
        response = client.get("/api/field/summary")
        
        assert response.status_code == 500
        data = response.json()
        assert "Summary error" in data["error"]


class TestFieldAlertEndpoint:
    """Test field alert endpoint."""

    def test_trigger_field_alert_success(self, client):
        """Should trigger field alert successfully."""
        alert_data = {"message": "Test alert", "level": "warning"}
        
        response = client.post("/api/field/alert", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Alert triggered"
        assert data["level"] == "warning"
        assert data["text"] == "Test alert"

    def test_trigger_field_alert_default_values(self, client):
        """Should use default values for alert."""
        response = client.post("/api/field/alert", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Alert triggered"
        assert data["level"] == "info"
        assert data["text"] == "Test alert"

    def test_trigger_field_alert_invalid_json(self, client):
        """Should handle invalid JSON."""
        response = client.post("/api/field/alert", data="invalid json")
        
        assert response.status_code == 422  # FastAPI validation error