from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.reporting_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with (
        patch(
            "birdnetpi.wrappers.reporting_manager_wrapper.ReportingManager"
        ) as mock_reporting_manager,
        patch(
            "birdnetpi.wrappers.reporting_manager_wrapper.FilePathResolver"
        ) as mock_file_path_resolver,
        patch(
            "birdnetpi.wrappers.reporting_manager_wrapper.ConfigFileParser"
        ) as mock_config_file_parser,
        patch(
            "birdnetpi.services.database_service.DatabaseService"
        ) as mock_database_service,
    ):
        mock_file_path_resolver_instance = mock_file_path_resolver.return_value
        mock_file_path_resolver_instance.get_birdnet_pi_config_path.return_value = str(
            tmp_path / "birdnet_pi_config.yaml"
        )
        (tmp_path / "birdnet_pi_config.yaml").touch()
        yield {
            "mock_reporting_manager": mock_reporting_manager,
            "mock_file_path_resolver": mock_file_path_resolver,
            "mock_config_file_parser": mock_config_file_parser,
            "mock_database_service": mock_database_service,
        }


def test_most_recent_action(mock_dependencies):
    """Should call get_most_recent_detections when action is 'most_recent'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="most_recent", limit=10),
    ):
        main_cli()
        mock_dependencies[
            "mock_reporting_manager"
        ].return_value.get_most_recent_detections.assert_called_once_with(10)


def test_spectrogram_action(mock_dependencies):
    """Should call generate_spectrogram when action is 'spectrogram'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="spectrogram", audio_file="test.wav", output_image="test.png"
        ),
    ):
        main_cli()
        mock_dependencies[
            "mock_reporting_manager"
        ].return_value.generate_spectrogram.assert_called_once_with(
            "test.wav", "test.png"
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
