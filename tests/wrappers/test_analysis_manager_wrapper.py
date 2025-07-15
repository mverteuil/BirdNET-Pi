import argparse
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.wrappers.analysis_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with (
        patch(
            "birdnetpi.managers.database_manager.DatabaseManager"
        ) as mock_database_manager,
        patch("birdnetpi.services.file_manager.FileManager") as mock_file_manager,
        patch(
            "birdnetpi.utils.file_path_resolver.FilePathResolver"
        ) as mock_file_path_resolver,
        patch(
            "birdnetpi.wrappers.analysis_manager_wrapper.ConfigFileParser"
        ) as mock_config_file_parser,
        patch(
            "birdnetpi.wrappers.analysis_manager_wrapper.AnalysisManager"
        ) as mock_analysis_manager,
    ):
        # Configure mocks
        mock_config_instance = MagicMock(spec=BirdNETConfig)
        mock_config_instance.database = MagicMock(path=str(tmp_path / "mock_db.db"))
        mock_config_instance.data = MagicMock(
            recordings_dir=str(tmp_path / "mock_recordings")
        )

        mock_config_parser_instance = mock_config_file_parser.return_value
        mock_config_parser_instance.load_config.return_value = mock_config_instance

        mock_file_path_resolver_instance = mock_file_path_resolver.return_value
        mock_file_path_resolver_instance.get_birdnet_conf_path.return_value = str(
            tmp_path / "birdnet.conf"
        )
        mock_file_path_resolver_instance.get_birdnet_pi_config_path.return_value = str(
            tmp_path / "birdnet_pi_config.yaml"
        )

        mock_analysis_manager_instance = MagicMock()
        mock_analysis_manager_instance.process_recordings = MagicMock()
        mock_analysis_manager_instance.extract_new_birdsounds = MagicMock()
        mock_analysis_manager.return_value = mock_analysis_manager_instance

        yield {
            "mock_config_file_parser": mock_config_file_parser,
            "mock_database_manager": mock_database_manager,
            "mock_file_manager": mock_file_manager,
            "mock_analysis_manager": mock_analysis_manager,
            "mock_file_path_resolver": mock_file_path_resolver,
            "mock_analysis_manager_instance": mock_analysis_manager_instance,
            "mock_config_instance": mock_config_instance,
        }


def test_process_recordings_action(mock_dependencies):
    """Should call process_recordings when action is 'process_recordings'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(action="process_recordings"),
    ):
        main_cli()
        mock_dependencies[
            "mock_analysis_manager_instance"
        ].process_recordings.assert_called_once()
        mock_dependencies[
            "mock_analysis_manager_instance"
        ].extract_new_birdsounds.assert_not_called()


def test_extract_new_birdsounds_action(mock_dependencies):
    """Should call extract_new_birdsounds when action is 'extract_new_birdsounds'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(action="extract_new_birdsounds"),
    ):
        main_cli()
        mock_dependencies[
            "mock_analysis_manager_instance"
        ].extract_new_birdsounds.assert_called_once()
        mock_dependencies[
            "mock_analysis_manager_instance"
        ].process_recordings.assert_not_called()


def test_unknown_action_raises_error(mock_dependencies):
    """Should raise an error for an unknown action."""
    with (
        patch(
            "argparse.ArgumentParser.parse_args",
            return_value=argparse.Namespace(action="unknown_action"),
        ),
        patch("argparse.ArgumentParser.error") as mock_error,
    ):
        main_cli()
        mock_error.assert_called_once_with("Unknown action: unknown_action")
