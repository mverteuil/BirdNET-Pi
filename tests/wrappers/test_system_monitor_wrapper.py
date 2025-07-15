from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.system_monitor_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with patch(
        "birdnetpi.wrappers.system_monitor_wrapper.SystemMonitor"
    ) as mock_system_monitor:
        mock_system_monitor_instance = mock_system_monitor.return_value
        mock_system_monitor_instance.check_disk_space.return_value = (True, "OK")
        yield {"mock_system_monitor": mock_system_monitor}


def test_disk_check_action(mock_dependencies):
    """Should call check_disk_space when action is 'disk_check'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="disk_check", path=".", threshold=10),
    ):
        main_cli()
        mock_dependencies[
            "mock_system_monitor"
        ].return_value.check_disk_space.assert_called_once_with(".", 10)


def test_dump_logs_action(mock_dependencies):
    """Should call dump_logs when action is 'dump_logs'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="dump_logs", log_file="/var/log/syslog"),
    ):
        main_cli()
        mock_dependencies[
            "mock_system_monitor"
        ].return_value.dump_logs.assert_called_once_with("/var/log/syslog")


def test_extra_info_action(mock_dependencies):
    """Should call get_extra_info when action is 'extra_info'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="extra_info"),
    ):
        main_cli()
        mock_dependencies[
            "mock_system_monitor"
        ].return_value.get_extra_info.assert_called_once()


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
