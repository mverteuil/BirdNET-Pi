from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.service_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with patch(
        "birdnetpi.wrappers.service_manager_wrapper.ServiceManager"
    ) as mock_service_manager:
        yield {"mock_service_manager": mock_service_manager}


def test_restart_services_action(mock_dependencies):
    """Should call restart_services when action is 'restart_services'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="restart_services", services=["test_service1", "test_service2"]
        ),
    ):
        main_cli()
        mock_dependencies[
            "mock_service_manager"
        ].return_value.restart_services.assert_called_once_with(
            ["test_service1", "test_service2"]
        )


def test_unknown_action_raises_error(mock_dependencies):
    """Should raise an error for an unknown action."""
    with (
        patch(
            "argparse.ArgumentParser.parse_args",
            return_value=MagicMock(action="unknown_action"),
        ),
        patch("argparse.ArgumentParser.error") as mock_error,
    ):
        main_cli()
        mock_error.assert_called_once_with("Unknown action: unknown_action")
