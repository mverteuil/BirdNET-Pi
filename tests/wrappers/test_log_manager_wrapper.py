from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.log_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    mock_log_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.log_manager_wrapper.LogManager", mock_log_manager_class
    )

    yield {"mock_log_manager_class": mock_log_manager_class}


def test_get_logs_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate LogManager and call get_logs."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="get_logs", limit=100),
    ):
        main_cli()

        mock_dependencies["mock_log_manager_class"].assert_called_once()
        instance = mock_dependencies["mock_log_manager_class"].return_value
        instance.get_logs.assert_called_once_with()
