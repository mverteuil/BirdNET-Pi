from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.system_monitor_wrapper import main_cli


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    mock_system_monitor_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.system_monitor_wrapper.SystemMonitor",
        mock_system_monitor_class,
    )

    yield {"mock_system_monitor_class": mock_system_monitor_class}


def test_extra_info_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate SystemMonitor and call get_extra_info."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="extra_info"),
    ):
        main_cli()

        mock_dependencies["mock_system_monitor_class"].assert_called_once()
        instance = mock_dependencies["mock_system_monitor_class"].return_value
        instance.get_extra_info.assert_called_once()
