from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.system.service_strategies import (
    ServiceManagementStrategy,
    ServiceStrategySelector,
)
from birdnetpi.system.system_control import SystemControlService


class TestSystemControlService:
    """Tests for the SystemControlService class, ensuring it correctly uses the strategy pattern."""

    @pytest.fixture
    def mock_strategy(self):
        """Fixture to provide a mock service strategy."""
        return MagicMock(spec=ServiceManagementStrategy)

    @pytest.fixture(autouse=True)
    def setup_system_control_service(self, mock_strategy):
        """Set up SystemControlService with a mocked strategy for each test."""
        with patch.object(ServiceStrategySelector, "get_strategy", return_value=mock_strategy):
            self.service_manager = SystemControlService()
            self.mock_strategy = mock_strategy

    def test_should_call_start_service_on_strategy(self):
        """Should delegate start_service call to the selected strategy."""
        service_name = "test_service"
        self.service_manager.start_service(service_name)
        self.mock_strategy.start_service.assert_called_once_with(service_name)  # type: ignore[attr-defined]

    def test_should_call_stop_service_on_strategy(self):
        """Should delegate stop_service call to the selected strategy."""
        service_name = "test_service"
        self.service_manager.stop_service(service_name)
        self.mock_strategy.stop_service.assert_called_once_with(service_name)  # type: ignore[attr-defined]

    def test_should_call_restart_service_on_strategy(self):
        """Should delegate restart_service call to the selected strategy."""
        service_name = "test_service"
        self.service_manager.restart_service(service_name)
        self.mock_strategy.restart_service.assert_called_once_with(service_name)  # type: ignore[attr-defined]

    def test_should_call_enable_service_on_strategy(self):
        """Should delegate enable_service call to the selected strategy."""
        service_name = "test_service"
        self.service_manager.enable_service(service_name)
        self.mock_strategy.enable_service.assert_called_once_with(service_name)  # type: ignore[attr-defined]

    def test_should_call_disable_service_on_strategy(self):
        """Should delegate disable_service call to the selected strategy."""
        service_name = "test_service"
        self.service_manager.disable_service(service_name)
        self.mock_strategy.disable_service.assert_called_once_with(service_name)  # type: ignore[attr-defined]

    def test_should_call_get_service_status_on_strategy(self):
        """Should delegate get_service_status call to strategy and return its result."""
        service_name = "test_service"
        self.mock_strategy.get_service_status.return_value = "active"  # type: ignore[attr-defined]
        status = self.service_manager.get_service_status(service_name)
        self.mock_strategy.get_service_status.assert_called_once_with(service_name)  # type: ignore[attr-defined]
        assert status == "active"

    def test_should_call_restart_service_for_each_service_in_list(self):
        """Should call restart_service on the strategy for each service in the list."""
        services = ["service1", "service2", "service3"]
        self.service_manager.restart_services(services)
        assert self.mock_strategy.restart_service.call_count == len(services)  # type: ignore[attr-defined]
        self.mock_strategy.restart_service.assert_any_call("service1")  # type: ignore[attr-defined]
        self.mock_strategy.restart_service.assert_any_call("service2")  # type: ignore[attr-defined]
        self.mock_strategy.restart_service.assert_any_call("service3")  # type: ignore[attr-defined]
