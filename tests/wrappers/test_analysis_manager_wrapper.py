from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.analysis_manager_wrapper import main_cli


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
        self.model = "mock_model"
        self.sf_thresh = 0.1
        self.confidence = 0.7
        self.sensitivity = 1.0
        self.latitude = 0.0
        self.longitude = 0.0
        self.week = 1
        self.overlap = 0.5
        self.cutoff = 0.5
        self.privacy_threshold = 0.5


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

    mock_analysis_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.AnalysisManager",
        mock_analysis_manager_class,
    )

    mock_db_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.DatabaseService",
        mock_db_service_class,
    )

    mock_file_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.FileManager",
        mock_file_manager_class,
    )

    mock_detection_manager_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.DetectionManager",
        mock_detection_manager_class,
    )

    mock_analysis_client_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.AnalysisClientService",
        mock_analysis_client_service_class,
    )

    mock_audio_processor_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.AudioProcessorService",
        mock_audio_processor_service_class,
    )

    mock_audio_extraction_service_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.AudioExtractionService",
        mock_audio_extraction_service_class,
    )

    mock_detection_event_publisher_class = MagicMock()
    monkeypatch.setattr(
        "birdnetpi.wrappers.analysis_manager_wrapper.DetectionEventPublisher",
        mock_detection_event_publisher_class,
    )

    yield {
        "mock_analysis_manager_class": mock_analysis_manager_class,
        "fake_config": fake_config,
    }


def test_process_recordings_action_instantiates_and_calls_correctly(mock_dependencies):
    """Should instantiate AnalysisManager and call process_audio_for_analysis."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="process_recordings", audio_file_path="/mock/audio/file.wav"),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_analysis_manager_class"].assert_called_once()

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_analysis_manager_class"].return_value
        instance.process_audio_for_analysis.assert_called_once_with("/mock/audio/file.wav")


def test_extract_new_birdsounds_action_instantiates_and_calls_correctly(
    mock_dependencies,
):
    """Should instantiate AnalysisManager and call extract_new_birdsounds."""
    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(action="extract_new_birdsounds", audio_file_path=None),
    ):
        main_cli()

        # Verify that the manager was instantiated correctly
        mock_dependencies["mock_analysis_manager_class"].assert_called_once()

        # Verify that the correct method was called on the instance
        instance = mock_dependencies["mock_analysis_manager_class"].return_value
        instance.extract_new_birdsounds.assert_called_once()
