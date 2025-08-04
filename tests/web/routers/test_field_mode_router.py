import json
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from birdnetpi.web.routers.field_mode_router import (
    get_detection_manager,
    get_gps_service,
    get_hardware_monitor,
    router,
)


@pytest.fixture
def mock_app():
    """Create a FastAPI app with mocked app state."""
    app = FastAPI()
    
    # Set up app state with mocks
    app.state.detections = MagicMock()
    app.state.gps_service = MagicMock()
    app.state.hardware_monitor = MagicMock()
    app.state.templates = MagicMock()
    
    app.include_router(router)
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

    def test_get_gps_service_available(self):
        """Should return GPS service when available."""
        request = MagicMock(spec=Request)
        request.app.state.gps_service = "mock_gps_service"
        result = get_gps_service(request)
        assert result == "mock_gps_service"

    def test_get_gps_service_unavailable(self):
        """Should return None when GPS service not available."""
        request = MagicMock(spec=Request)
        # Mock app.state without gps_service attribute
        request.app.state = MagicMock()
        del request.app.state.gps_service  # Remove the attribute
        with patch('builtins.hasattr', return_value=False):
            result = get_gps_service(request)
            assert result is None

    def test_get_hardware_monitor_available(self):
        """Should return hardware monitor when available."""
        request = MagicMock(spec=Request)
        request.app.state.hardware_monitor = "mock_hardware_monitor"
        result = get_hardware_monitor(request)
        assert result == "mock_hardware_monitor"

    def test_get_hardware_monitor_unavailable(self):
        """Should return None when hardware monitor not available."""
        request = MagicMock(spec=Request)
        # Mock app.state without hardware_monitor attribute
        request.app.state = MagicMock()
        del request.app.state.hardware_monitor
        with patch('builtins.hasattr', return_value=False):
            result = get_hardware_monitor(request)
            assert result is None


class TestGPSEndpoints:
    """Test GPS-related field mode endpoints."""

    def test_get_gps_status_service_not_available(self, client):
        """Should return error when GPS service not initialized."""
        # Set gps_service to None to simulate unavailable service
        client.app.state.gps_service = None

        response = client.get("/api/gps/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["available"] is False
        assert "GPS service not initialized" in data["message"]

    def test_get_gps_status_success(self, client):
        """Should return GPS status when service available."""
        mock_status = {
            "enabled": True,
            "available": True,
            "satellites": 8,
            "accuracy": 3.2
        }
        client.app.state.gps_service.get_gps_status.return_value = mock_status

        response = client.get("/api/gps/status")

        assert response.status_code == 200
        assert response.json() == mock_status

    def test_get_gps_status_exception(self, client):
        """Should handle GPS status exceptions gracefully."""
        client.app.state.gps_service.get_gps_status.side_effect = Exception("GPS error")
        client.app.state.gps_service.enable_gps = True

        response = client.get("/api/gps/status")

        assert response.status_code == 500
        data = response.json()
        assert data["enabled"] is True
        assert data["available"] is False
        assert "GPS error" in data["error"]

    def test_get_current_location_service_not_available(self, client):
        """Should return 404 when GPS service not available."""
        client.app.state.gps_service = None

        response = client.get("/api/gps/location")

        assert response.status_code == 404
        assert "GPS service not available" in response.json()["error"]

    def test_get_current_location_success(self, client):
        """Should return current GPS location."""
        mock_location = MagicMock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060
        mock_location.altitude = 10.5
        mock_location.accuracy = 3.2
        mock_location.timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_location.satellite_count = 8

        client.app.state.gps_service.get_current_location.return_value = mock_location

        response = client.get("/api/gps/location")

        assert response.status_code == 200
        data = response.json()
        assert data["latitude"] == 40.7128
        assert data["longitude"] == -74.0060
        assert data["altitude"] == 10.5
        assert data["accuracy"] == 3.2
        assert data["satellite_count"] == 8
        assert "2023-01-01T12:00:00" in data["timestamp"]

    def test_get_current_location_no_fix(self, client):
        """Should return 404 when no GPS fix available."""
        client.app.state.gps_service.get_current_location.return_value = None

        response = client.get("/api/gps/location")

        assert response.status_code == 404
        assert "No GPS fix available" in response.json()["error"]

    def test_get_current_location_exception(self, client):
        """Should handle GPS location exceptions."""
        client.app.state.gps_service.get_current_location.side_effect = Exception("Location error")

        response = client.get("/api/gps/location")

        assert response.status_code == 500
        assert "Location error" in response.json()["error"]


class TestHardwareEndpoints:
    """Test hardware monitoring field mode endpoints."""

    def test_get_hardware_status_service_not_available(self, client):
        """Should return unavailable status when hardware monitoring not enabled."""
        client.app.state.hardware_monitor = None

        response = client.get("/api/hardware/status")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "Hardware monitoring not enabled" in data["message"]
        assert data["components"] == {}

    def test_get_hardware_status_success(self, client):
        """Should return hardware status when monitoring available."""
        mock_status = {
            "overall_status": "healthy",
            "components": {
                "cpu": {"status": "normal", "temperature": 45.2},
                "memory": {"status": "normal", "usage": 65.5}
            }
        }
        client.app.state.hardware_monitor.get_health_summary.return_value = mock_status

        response = client.get("/api/hardware/status")

        assert response.status_code == 200
        assert response.json() == mock_status

    def test_get_hardware_status_exception(self, client):
        """Should handle hardware status exceptions."""
        client.app.state.hardware_monitor.get_health_summary.side_effect = Exception("Hardware error")

        response = client.get("/api/hardware/status")

        assert response.status_code == 500
        assert "Hardware error" in response.json()["error"]

    def test_get_component_status_service_not_available(self, client):
        """Should return 404 when hardware monitoring not available."""
        client.app.state.hardware_monitor = None

        response = client.get("/api/hardware/component/cpu")

        assert response.status_code == 404
        assert "Hardware monitoring not available" in response.json()["error"]

    def test_get_component_status_success(self, client):
        """Should return specific component status."""
        mock_component = MagicMock()
        mock_component.name = "cpu"
        mock_component.status.value = "healthy"
        mock_component.message = "CPU temperature normal"
        mock_component.last_check = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_component.details = {"temperature": 45.2, "usage": 25.3}

        client.app.state.hardware_monitor.get_component_status.return_value = mock_component

        response = client.get("/api/hardware/component/cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "cpu"
        assert data["status"] == "healthy"
        assert data["message"] == "CPU temperature normal"
        assert "2023-01-01T12:00:00" in data["last_check"]
        assert data["details"]["temperature"] == 45.2

    def test_get_component_status_not_found(self, client):
        """Should return 404 for unknown component."""
        client.app.state.hardware_monitor.get_component_status.return_value = None

        response = client.get("/api/hardware/component/unknown")

        assert response.status_code == 404
        assert "Component 'unknown' not found" in response.json()["error"]

    def test_get_component_status_exception(self, client):
        """Should handle component status exceptions."""
        client.app.state.hardware_monitor.get_component_status.side_effect = Exception("Component error")

        response = client.get("/api/hardware/component/cpu")

        assert response.status_code == 500
        assert "Component error" in response.json()["error"]


class TestFieldSummaryEndpoint:
    """Test field summary endpoint."""

    @patch('birdnetpi.web.routers.field_mode_router.datetime')
    def test_get_field_summary_success(self, mock_datetime, client):
        """Should return comprehensive field summary."""
        # Mock datetime
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # Setup detection manager
        client.app.state.detections.get_detections_count_by_date.return_value = 15
        
        mock_detection1 = MagicMock()
        mock_detection1.species = "Robin"
        mock_detection1.confidence = 0.85
        mock_detection1.timestamp = mock_now
        
        mock_detection2 = MagicMock()
        mock_detection2.species = "Sparrow"
        mock_detection2.confidence = 0.92
        mock_detection2.timestamp = mock_now
        
        client.app.state.detections.get_recent_detections.return_value = [mock_detection1, mock_detection2]

        # Setup GPS service
        mock_gps_status = {"enabled": True, "available": True, "satellites": 8}
        client.app.state.gps_service.get_gps_status.return_value = mock_gps_status

        # Setup hardware monitor
        mock_hw_status = {"overall_status": "healthy", "components": {"cpu": "normal"}}
        client.app.state.hardware_monitor.get_health_summary.return_value = mock_hw_status

        response = client.get("/api/field/summary")

        assert response.status_code == 200
        data = response.json()
        assert "2023-01-01T12:00:00" in data["timestamp"]
        assert data["detections"]["today_count"] == 15
        assert len(data["detections"]["recent"]) == 2
        assert data["detections"]["recent"][0]["species"] == "Robin"
        assert data["detections"]["recent"][0]["confidence"] == 0.85
        assert data["gps"] == mock_gps_status
        assert data["hardware"] == mock_hw_status

    @patch('birdnetpi.web.routers.field_mode_router.datetime')
    def test_get_field_summary_no_gps_service(self, mock_datetime, client):
        """Should handle missing GPS service gracefully."""
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        client.app.state.detections.get_detections_count_by_date.return_value = 10
        client.app.state.detections.get_recent_detections.return_value = []
        client.app.state.gps_service = None
        client.app.state.hardware_monitor.get_health_summary.return_value = {"overall_status": "healthy"}

        response = client.get("/api/field/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["gps"]["enabled"] is False

    @patch('birdnetpi.web.routers.field_mode_router.datetime')
    def test_get_field_summary_no_hardware_monitor(self, mock_datetime, client):
        """Should handle missing hardware monitor gracefully."""
        mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        client.app.state.detections.get_detections_count_by_date.return_value = 10
        client.app.state.detections.get_recent_detections.return_value = []
        client.app.state.gps_service.get_gps_status.return_value = {"enabled": True}
        client.app.state.hardware_monitor = None

        response = client.get("/api/field/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["hardware"]["overall_status"] == "unknown"

    def test_get_field_summary_exception(self, client):
        """Should handle field summary exceptions."""
        client.app.state.detections.get_detections_count_by_date.side_effect = Exception("Summary error")

        response = client.get("/api/field/summary")

        assert response.status_code == 500
        assert "Summary error" in response.json()["error"]


class TestFieldAlertEndpoint:
    """Test field alert endpoint."""

    def test_trigger_field_alert_success(self, client):
        """Should trigger field alert successfully."""
        alert_data = {
            "message": "Battery low warning",
            "level": "warning"
        }

        response = client.post("/api/field/alert", json=alert_data)

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Alert triggered"
        assert data["level"] == "warning"
        assert data["text"] == "Battery low warning"

    def test_trigger_field_alert_default_values(self, client):
        """Should use default values for missing fields."""
        response = client.post("/api/field/alert", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Alert triggered"
        assert data["level"] == "info"
        assert data["text"] == "Test alert"

    def test_trigger_field_alert_invalid_json(self, client):
        """Should handle invalid JSON gracefully."""
        response = client.post("/api/field/alert", data="invalid json")

        assert response.status_code == 500
        assert "error" in response.json()


class TestFieldModeTemplate:
    """Test field mode template endpoint."""

    def test_get_field_mode_template_response(self, client):
        """Should attempt to render field mode template."""
        # Mock the template response to avoid file system dependencies
        from fastapi.responses import HTMLResponse
        
        # Create a mock HTMLResponse
        mock_response = HTMLResponse(content="<html><body>Field Mode</body></html>")
        client.app.state.templates.TemplateResponse.return_value = mock_response
        
        response = client.get("/field")
        
        # Verify template was called and response received
        client.app.state.templates.TemplateResponse.assert_called_once()
        call_args = client.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "field_mode.html"
        assert "request" in call_args[0][1]
        assert response.status_code == 200


class TestLocationHistoryEndpoint:
    """Test location history endpoint."""

    def test_get_location_history_success(self, client):
        """Should return location history successfully."""
        # Mock GPS service with location history
        mock_location1 = MagicMock()
        mock_location1.latitude = 40.7128
        mock_location1.longitude = -74.0060
        mock_location1.altitude = 10.0
        mock_location1.accuracy = 5.0
        mock_location1.timestamp = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_location1.satellite_count = 8

        mock_location2 = MagicMock()
        mock_location2.latitude = 40.7130
        mock_location2.longitude = -74.0062
        mock_location2.altitude = 12.0
        mock_location2.accuracy = 3.0
        mock_location2.timestamp = datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        mock_location2.satellite_count = 10

        client.app.state.gps_service.get_location_history.return_value = [mock_location1, mock_location2]

        response = client.get("/api/gps/history?hours=24")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["locations"]) == 2
        
        # Check first location
        loc1 = data["locations"][0]
        assert loc1["latitude"] == 40.7128
        assert loc1["longitude"] == -74.0060
        assert loc1["altitude"] == 10.0
        assert loc1["accuracy"] == 5.0
        assert loc1["satellite_count"] == 8
        assert "2025-01-15T12:00:00" in loc1["timestamp"]

    def test_get_location_history_no_gps_service(self, client):
        """Should return 404 when GPS service not available."""
        client.app.state.gps_service = None

        response = client.get("/api/gps/history")

        assert response.status_code == 404
        assert response.json()["error"] == "GPS service not available"

    def test_get_location_history_service_exception(self, client):
        """Should handle GPS service exceptions."""
        client.app.state.gps_service.get_location_history.side_effect = Exception("GPS history error")

        response = client.get("/api/gps/history")

        assert response.status_code == 500
        assert "GPS history error" in response.json()["error"]

    def test_get_location_history_with_custom_hours(self, client):
        """Should accept custom hours parameter."""
        client.app.state.gps_service.get_location_history.return_value = []

        response = client.get("/api/gps/history?hours=48")

        assert response.status_code == 200
        # Verify the service was called with the custom hours parameter
        client.app.state.gps_service.get_location_history.assert_called_once_with(48)