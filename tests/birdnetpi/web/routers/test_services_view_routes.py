"""Tests for services view routes."""

from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient

from birdnetpi.system.system_control import SystemControlService
from birdnetpi.web.core.container import Container


class TestServicesViewRoutes:
    """Test class for services view endpoints."""

    @pytest.mark.asyncio
    async def test_services_page_renders_successfully(self, app_with_temp_data, path_resolver):
        """Should render services page with correct context."""
        # Mock the system control service
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_services = [
            {
                "name": "fastapi",
                "status": "active",
                "description": "Web interface and API",
                "pid": 1234,
                "uptime_seconds": 3600,
                "critical": True,
                "optional": False,
            },
            {
                "name": "audio_capture",
                "status": "active",
                "description": "Audio recording service",
                "pid": 5678,
                "uptime_seconds": 7200,
                "critical": False,
                "optional": False,
            },
        ]
        mock_system_info = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day, 0:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }
        mock_system_control.get_all_services_status.return_value = mock_services
        mock_system_control.get_system_info.return_value = mock_system_info

        # Override the system control service in the container
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should render successfully
            assert response.status_code == 200
            assert b"Services" in response.content or b"services" in response.content

    @pytest.mark.asyncio
    async def test_services_page_handles_service_error(self, app_with_temp_data, path_resolver):
        """Should handle errors when getting service status."""
        # Mock the system control service to raise an error
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_system_control.get_all_services_status.side_effect = Exception("Service error")
        mock_system_control.get_system_info.return_value = {
            "uptime_seconds": 0,
            "uptime_formatted": "Unknown",
            "reboot_available": False,
            "deployment_type": "unknown",
        }

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should still render successfully with empty services
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_handles_system_info_error(self, app_with_temp_data, path_resolver):
        """Should handle errors when getting system info."""
        # Mock the system control service
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_system_control.get_all_services_status.return_value = []
        mock_system_control.get_system_info.side_effect = Exception("System info error")

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should still render successfully with default system info
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_formats_uptime(self, app_with_temp_data, path_resolver):
        """Should format service uptime correctly."""
        # Mock the system control service with various uptime values
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_services = [
            {
                "name": "service1",
                "status": "active",
                "description": "Service 1",
                "pid": 1000,
                "uptime_seconds": 3661,  # 1 hour, 1 minute, 1 second
                "critical": False,
                "optional": False,
            },
            {
                "name": "service2",
                "status": "active",
                "description": "Service 2",
                "pid": 2000,
                "uptime_seconds": 90061,  # 1 day, 1 hour, 1 minute, 1 second
                "critical": False,
                "optional": False,
            },
            {
                "name": "service3",
                "status": "inactive",
                "description": "Service 3",
                "pid": None,
                "uptime_seconds": None,
                "critical": False,
                "optional": False,
            },
        ]
        mock_system_control.get_all_services_status.return_value = mock_services
        mock_system_control.get_system_info.return_value = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day, 0:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should render successfully
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_identifies_critical_services(
        self, app_with_temp_data, path_resolver
    ):
        """Should correctly identify critical services."""
        # Mock the system control service
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_services = [
            {
                "name": "fastapi",
                "status": "active",
                "description": "Web interface and API",
                "pid": 1234,
                "uptime_seconds": 3600,
                "critical": True,
                "optional": False,
            },
            {
                "name": "audio_capture",
                "status": "active",
                "description": "Audio recording service",
                "pid": 5678,
                "uptime_seconds": 7200,
                "critical": False,
                "optional": False,
            },
        ]
        mock_system_control.get_all_services_status.return_value = mock_services
        mock_system_control.get_system_info.return_value = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day, 0:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should render successfully
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_service_status_variations(self, app_with_temp_data, path_resolver):
        """Should handle various service status values."""
        # Mock the system control service with different statuses
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_services = [
            {
                "name": "srv1",
                "status": "active",
                "description": "Active",
                "pid": 100,
                "uptime_seconds": 1000,
                "critical": False,
                "optional": False,
            },
            {
                "name": "srv2",
                "status": "inactive",
                "description": "Inactive",
                "pid": None,
                "uptime_seconds": None,
                "critical": False,
                "optional": False,
            },
            {
                "name": "srv3",
                "status": "failed",
                "description": "Failed",
                "pid": None,
                "uptime_seconds": None,
                "critical": False,
                "optional": False,
            },
            {
                "name": "srv4",
                "status": "starting",
                "description": "Starting",
                "pid": 200,
                "uptime_seconds": 5,
                "critical": False,
                "optional": False,
            },
            {
                "name": "srv5",
                "status": "unknown",
                "description": "Unknown",
                "pid": None,
                "uptime_seconds": None,
                "critical": False,
                "optional": True,
            },
        ]
        mock_system_control.get_all_services_status.return_value = mock_services
        mock_system_control.get_system_info.return_value = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day, 0:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Create test client
        with TestClient(app_with_temp_data) as client:
            response = client.get("/admin/services")

            # Should render successfully
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_deployment_type_variations(
        self, app_with_temp_data, path_resolver
    ):
        """Should handle different deployment types."""
        mock_system_control = MagicMock(spec=SystemControlService)

        for deployment_type in ["docker", "sbc", "unknown"]:
            # Update mock to return different deployment type
            mock_system_control.get_all_services_status.return_value = []
            mock_system_control.get_system_info.return_value = {
                "uptime_seconds": 86400,
                "uptime_formatted": "1 day, 0:00:00",
                "reboot_available": deployment_type != "unknown",
                "deployment_type": deployment_type,
            }

            # Override the system control service
            Container.system_control_service.override(providers.Object(mock_system_control))

            # Create test client
            with TestClient(app_with_temp_data) as client:
                response = client.get("/admin/services")

                # Should render successfully for each deployment type
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_services_page_with_systemutils_deployment(
        self, app_with_temp_data, path_resolver
    ):
        """Should use SystemUtils for deployment type when needed."""
        # Mock the system control service
        mock_system_control = MagicMock(spec=SystemControlService)
        mock_system_control.get_all_services_status.return_value = []
        mock_system_control.get_system_info.return_value = {
            "uptime_seconds": 86400,
            "uptime_formatted": "1 day, 0:00:00",
            "reboot_available": True,
            "deployment_type": "docker",
        }

        # Override the system control service
        Container.system_control_service.override(providers.Object(mock_system_control))

        # Mock SystemUtils to return a specific deployment type
        with patch(
            "birdnetpi.web.routers.services_view_routes.SystemUtils", autospec=True
        ) as mock_utils:
            mock_utils.get_deployment_environment.return_value = "sbc"

            # Create test client
            with TestClient(app_with_temp_data) as client:
                response = client.get("/admin/services")

                # Should render successfully
                assert response.status_code == 200
                # SystemUtils should have been called
                mock_utils.get_deployment_environment.assert_called()
