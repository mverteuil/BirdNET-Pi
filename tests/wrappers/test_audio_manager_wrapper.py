from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.audio_manager_wrapper import main_cli


@pytest.fixture
def mock_dependencies(tmp_path):
    """Fixture to mock all external dependencies."""
    with (
        patch(
            "birdnetpi.wrappers.audio_manager_wrapper.AudioManager"
        ) as mock_audio_manager,
        patch(
            "birdnetpi.wrappers.audio_manager_wrapper.FilePathResolver"
        ) as mock_file_path_resolver,
        patch(
            "birdnetpi.wrappers.audio_manager_wrapper.ConfigFileParser"
        ) as mock_config_file_parser,
    ):
        mock_file_path_resolver_instance = mock_file_path_resolver.return_value
        mock_file_path_resolver_instance.get_birdnet_pi_config_path.return_value = str(
            tmp_path / "birdnet_pi_config.yaml"
        )
        (tmp_path / "birdnet_pi_config.yaml").touch()
        yield {
            "mock_audio_manager": mock_audio_manager,
            "mock_file_path_resolver": mock_file_path_resolver,
            "mock_config_file_parser": mock_config_file_parser,
        }


def test_livestream_action(mock_dependencies):
    """Should call livestream when action is 'livestream'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="livestream", output_url="test_url"),
    ):
        main_cli()
        mock_dependencies[
            "mock_audio_manager"
        ].return_value.livestream.assert_called_once_with("test_url")


def test_record_action(mock_dependencies):
    """Should call record when action is 'record'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="record"),
    ):
        main_cli()
        mock_dependencies["mock_audio_manager"].return_value.record.assert_called_once()


def test_custom_record_action(mock_dependencies):
    """Should call custom_record when action is 'custom_record'."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="custom_record", duration=10, output_file="test.wav"
        ),
    ):
        main_cli()
        mock_dependencies[
            "mock_audio_manager"
        ].return_value.custom_record.assert_called_once_with(10, "test.wav")


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
