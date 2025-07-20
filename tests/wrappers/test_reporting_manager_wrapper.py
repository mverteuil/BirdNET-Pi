from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.reporting_manager_wrapper import main_cli


# Define simple, explicit "Fake" objects for the test
class FakeDataConfig:
    """A fake DataConfig for testing."""

    def __init__(self, db_path, recordings_dir):
        self.db_path = db_path
        self.recordings_dir = recordings_dir


class FakeConfig:
    """A fake BirdNETConfig for testing."""

    def __init__(self, db_path, recordings_dir):
        self.data = FakeDataConfig(db_path, recordings_dir)


@pytest.fixture
def mock_dependencies(tmp_path, monkeypatch):
    """Fixture to mock all external dependencies for this test module."""
    fake_config = FakeConfig(
        db_path=str(tmp_path / "test.db"),
        recordings_dir=str(tmp_path / "recordings"),
    )

    monkeypatch.setattr(
        "birdnetpi.utils.config_file_parser.ConfigFileParser.load_config",
        lambda self: fake_config,
    )

    mock_reporting_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.reporting_manager_wrapper.ReportingManager",
        mock_reporting_manager_class,
    )

    mock_db_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.reporting_manager_wrapper.DatabaseService",
        mock_db_service_class,
    )

    mock_detection_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.reporting_manager_wrapper.DetectionManager",
        mock_detection_manager_class,
    )

    mock_file_path_resolver_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.reporting_manager_wrapper.FilePathResolver",
        mock_file_path_resolver_class,
    )

    mock_config_parser_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.reporting_manager_wrapper.ConfigFileParser",
        mock_config_parser_class,
    )

    yield {
        "mock_reporting_manager_class": mock_reporting_manager_class,
        "fake_config": fake_config,
    }


def test_most_recent_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate ReportingManager and call get_most_recent_detections."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="most_recent", limit=5),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_reporting_manager_class"].assert_called_once()

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_reporting_manager_class"].return_value
        instance.get_most_recent_detections.assert_called_once_with(5)


def test_spectrogram_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate ReportingManager and call generate_spectrogram."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            action="spectrogram",
            audio_file="/mock/audio.wav",
            output_image="/mock/image.png",
        ),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_reporting_manager_class"].assert_called_once()

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_reporting_manager_class"].return_value
        instance.generate_spectrogram.assert_called_once_with(
            "/mock/audio.wav", "/mock/image.png"
        )
