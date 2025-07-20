from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.service_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    mock_service_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.service_manager_wrapper.ServiceManager",
        mock_service_manager_class,
    )

    yield {"mock_service_manager_class": mock_service_manager_class}


def test_restart_services_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate ServiceManager and call restart_services."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="restart_services", services=["test.service"]),
    ):
        main_cli()

        mock_dependencies["mock_service_manager_class"].assert_called_once()
        instance = mock_dependencies["mock_service_manager_class"].return_value
        instance.restart_services.assert_called_once_with(["test.service"])
