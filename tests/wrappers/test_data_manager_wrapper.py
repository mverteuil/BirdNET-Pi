from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.data_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with (
        patch(
            "birdnetpi.wrappers.data_manager_wrapper.DataManager"
        ) as mock_data_manager,
        patch(
            "birdnetpi.wrappers.data_manager_wrapper.FilePathResolver"
        ) as mock_file_path_resolver,
        patch(
            "birdnetpi.wrappers.data_manager_wrapper.ConfigFileParser"
        ) as mock_config_file_parser,
        patch(
            "birdnetpi.wrappers.data_manager_wrapper.DatabaseService"
        ) as mock_database_service,
        patch(
            "birdnetpi.wrappers.data_manager_wrapper.FileManager"
        ) as mock_file_manager,
    ):
        mock_file_path_resolver_instance = mock_file_path_resolver.return_value
        mock_file_path_resolver_instance.get_birdnet_pi_config_path.return_value = str(
            tmp_path / "birdnet_pi_config.yaml"
        )
        (tmp_path / "birdnet_pi_config.yaml").touch()
        yield {
            "mock_data_manager": mock_data_manager,
            "mock_file_path_resolver": mock_file_path_resolver,
            "mock_config_file_parser": mock_config_file_parser,
            "mock_database_service": mock_database_service,
            "mock_file_manager": mock_file_manager,
        }


def test_cleanup_action(mock_dependencies):
    """Should call cleanup when action is 'cleanup'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="cleanup"),
    ):
        main_cli()
        mock_dependencies["mock_data_manager"].return_value.cleanup.assert_called_once()


def test_clear_all_data_action(mock_dependencies):
    """Should call clear_all_data when action is 'clear_all_data'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="clear_all_data"),
    ):
        main_cli()
        mock_dependencies[
            "mock_data_manager"
        ].return_value.clear_all_data.assert_called_once()


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
