from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.managers.system_monitor import SystemMonitor
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.routers.overview_router import (
    get_overview_data,
    get_reporting_manager,
    get_system_monitor,
)


@pytest.fixture
def mock_system_monitor():
    """Return a mock SystemMonitor object."""
    monitor = MagicMock(spec=SystemMonitor)
    monitor.get_disk_usage.return_value = {"total": "100GB", "used": "50GB"}
    monitor.get_extra_info.return_value = {"cpu_temp": "45C"}
    return monitor


@pytest.fixture
def mock_detection_manager():
    """Return a mock DetectionManager object."""
    manager_instance_mock = MagicMock(spec=DetectionManager)
    manager_instance_mock.get_total_detections.return_value = 123
    return manager_instance_mock


@pytest.fixture
def mock_file_path_resolver():
    """Return a mock FilePathResolver object."""
    resolver = MagicMock(spec=FilePathResolver)
    resolver.get_birdnet_pi_config_path.return_value = "/mock/config.yaml"
    resolver.repo_root = "/mock/repo_root"  # Add this line
    return resolver


@pytest.fixture
def mock_config_file_parser():
    """Return a mock ConfigFileParser object."""
    parser = MagicMock(spec=ConfigFileParser)
    parser.load_config.return_value = MagicMock()
    parser.load_config.return_value.data = MagicMock()
    parser.load_config.return_value.data.db_path = "/mock/test.db"
    return parser


@pytest.fixture
def mock_request(mock_file_path_resolver, mock_config_file_parser):
    """Return a mock Request object."""
    request = MagicMock(spec=Request)
    request.app.state.file_resolver = mock_file_path_resolver
    request.app.state.file_resolver.repo_root = "/mock/repo_root"
    request.app.state.config = mock_config_file_parser.load_config.return_value
    return request


@pytest.fixture
def mock_reporting_manager(
    mock_detection_manager, mock_file_path_resolver, mock_config_file_parser
):
    """Return a mock ReportingManager object."""
    manager = MagicMock(spec=ReportingManager)
    manager.detection_manager = mock_detection_manager
    manager.file_path_resolver = mock_file_path_resolver
    manager.config = mock_config_file_parser.load_config.return_value
    manager.plotting_manager = MagicMock()
    manager.data_preparation_manager = MagicMock()
    manager.location_service = MagicMock()
    return manager


class TestOverviewRouter:
    """Test the overview router."""

    def test_get_system_monitor(self):
        """Test the get_system_monitor dependency."""
        monitor = get_system_monitor()
        assert isinstance(monitor, SystemMonitor)

    def test_get_reporting_manager(
        self, mock_request, mock_detection_manager, mock_file_path_resolver, mock_config_file_parser
    ):
        """Test the get_reporting_manager dependency."""
        # Create a mock DetectionManager instance with a mocked db_service
        mock_dm_instance = MagicMock(spec=DetectionManager)
        mock_dm_instance.db_service = MagicMock()
        mock_dm_instance.db_service.get_total_detections.return_value = 123

        # Patch the DetectionManager and ConfigFileParser within the function's scope
        with (
            patch(
                "birdnetpi.web.routers.overview_router.DetectionManager"
            ) as mock_detection_manager_class,
            patch(
                "birdnetpi.web.routers.overview_router.ConfigFileParser",
                return_value=mock_config_file_parser,
            ),
            patch(
                "birdnetpi.web.routers.overview_router.FilePathResolver",
                return_value=mock_file_path_resolver,
            ),
        ):
            mock_detection_manager_class.return_value = mock_dm_instance
            manager = get_reporting_manager(mock_request)
            assert isinstance(manager, ReportingManager)
            mock_detection_manager_class.assert_called_once_with("/mock/test.db")
            mock_file_path_resolver.get_birdnet_pi_config_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_overview_data(
        self, mock_system_monitor, mock_reporting_manager, mock_request
    ):
        """Test the get_overview_data endpoint."""
        with (
            patch(
                "birdnetpi.web.routers.overview_router.get_system_monitor",
                return_value=mock_system_monitor,
            ),
            patch(
                "birdnetpi.web.routers.overview_router.get_reporting_manager",
                return_value=mock_reporting_manager,
            ),
        ):
            response = await get_overview_data(mock_system_monitor, mock_reporting_manager)

            mock_system_monitor.get_disk_usage.assert_called_once()
            mock_system_monitor.get_extra_info.assert_called_once()

            assert response == {
                "disk_usage": {"total": "100GB", "used": "50GB"},
                "extra_info": {"cpu_temp": "45C"},
                "total_detections": 123,
            }
