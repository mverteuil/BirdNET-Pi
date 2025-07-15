from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.log_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with patch("birdnetpi.wrappers.log_manager_wrapper.LogManager") as mock_log_manager:
        yield {"mock_log_manager": mock_log_manager}


def test_get_logs_action(mock_dependencies):
    """Should call get_logs when action is 'get_logs'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="get_logs"),
    ):
        main_cli()
        mock_dependencies["mock_log_manager"].return_value.get_logs.assert_called_once()


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
