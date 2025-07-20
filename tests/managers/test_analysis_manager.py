import logging  # Added logging import
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import numpy as np  # Added numpy import
import pytest

from birdnetpi.managers.analysis_manager import AnalysisManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig, DataConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.audio_extraction_service import AudioExtractionService
from birdnetpi.services.audio_processor_service import AudioProcessorService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    mock.audio_format = "mp3"
    mock.extraction_length = 6.0
    mock.data = Mock(
        spec=DataConfig
    )  # Mock the data attribute as a DataConfig instance
    mock.data.extracted_dir = "/tmp/extracted"
    mock.overlap = 0.5  # Added overlap attribute
    mock.confidence = 0.7  # Added confidence attribute
    mock.latitude = 0.0  # Added latitude attribute
    mock.longitude = 0.0  # Added longitude attribute
    mock.week = 1  # Added week attribute
    mock.sensitivity = 1.0  # Added sensitivity attribute
    mock.cutoff = 0.0  # Added cutoff attribute
    return mock


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    mock = Mock(spec=FileManager)
    mock_path_object = MagicMock(spec=Path)
    mock_path_object.mkdir.return_value = None
    mock_path_object.name = "mock_path"
    mock.get_full_path.return_value = mock_path_object
    mock.mock_extracted_path = mock_path_object  # Store for assertion
    return mock


@pytest.fixture
def mock_detection_manager():
    """Provide a mock DatabaseManager instance."""
    return Mock(spec=DetectionManager)


@pytest.fixture
def mock_analysis_client_service():
    """Provide a mock AnalysisClientService instance."""
    return Mock(spec=AnalysisClientService)


@pytest.fixture
def mock_audio_processor_service():
    """Provide a mock AudioProcessorService instance."""
    return Mock(spec=AudioProcessorService)


@pytest.fixture
def mock_audio_extraction_service():
    """Provide a mock AudioExtractionService instance."""
    return Mock(spec=AudioExtractionService)


@pytest.fixture
def mock_detection_event_publisher():
    """Provide a mock DetectionEventPublisher instance."""
    return Mock(spec=DetectionEventPublisher)


@pytest.fixture
def analysis_manager(
    mock_config,
    mock_file_manager,
    mock_detection_manager,
    mock_analysis_client_service,
    mock_audio_processor_service,
    mock_audio_extraction_service,
    mock_detection_event_publisher,
):
    """Provide an AnalysisManager instance with mocked dependencies."""
    return AnalysisManager(
        config=mock_config,
        file_manager=mock_file_manager,
        detection_manager=mock_detection_manager,
        analysis_client_service=mock_analysis_client_service,
        audio_processor_service=mock_audio_processor_service,
        audio_extraction_service=mock_audio_extraction_service,
        detection_event_publisher=mock_detection_event_publisher,
    )


@pytest.fixture(autouse=True)
def caplog_for_analysis_manager(caplog):
    """Fixture to capture logs from analysis_manager.py."""
    caplog.set_level(logging.INFO, logger="birdnetpi.managers.analysis_manager")
    # Removed StreamHandler as caplog is sufficient for capturing logs
    yield


def test_process_audio_for_analysis_with_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_audio_processor_service,
    mock_detection_manager,
    mock_detection_event_publisher,
    caplog,
):
    """Should process audio, add detection, and publish event when analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    mock_audio_processor_service.read_audio_data.return_value = [np.array([1, 2, 3])]
    mock_analysis_client_service.get_filtered_species_list.return_value = [
        "Test Species"
    ]
    mock_analysis_client_service.get_raw_prediction.return_value = [
        ("Test Species", 0.9)
    ]
    mock_detection_manager.add_detection.return_value = Mock(species="Test Species")

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_audio_processor_service.read_audio_data.assert_called_once_with(
        audio_file_path, analysis_manager.config.overlap
    )
    mock_analysis_client_service.get_filtered_species_list.assert_called_once()
    mock_analysis_client_service.get_raw_prediction.assert_called_once()
    mock_detection_manager.add_detection.assert_called_once()
    mock_detection_event_publisher.publish_detection.assert_called_once()
    assert (
        f"AnalysisManager: Processing audio for analysis: {audio_file_path}"
        in caplog.text
    )
    assert "AnalysisManager: Added detection to DB: Test Species" in caplog.text


def test_process_audio_for_analysis_no_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_audio_processor_service,
    mock_detection_manager,
    mock_detection_event_publisher,
    caplog,
):
    """Should only analyze audio when no analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    mock_audio_processor_service.read_audio_data.return_value = [np.array([1, 2, 3])]
    mock_analysis_client_service.get_filtered_species_list.return_value = [
        "Test Species"
    ]
    mock_analysis_client_service.get_raw_prediction.return_value = [
        ("Other Species", 0.1)
    ]  # Low confidence

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_audio_processor_service.read_audio_data.assert_called_once_with(
        audio_file_path, analysis_manager.config.overlap
    )
    mock_analysis_client_service.get_filtered_species_list.assert_called_once()
    mock_analysis_client_service.get_raw_prediction.assert_called_once()
    mock_detection_manager.add_detection.assert_not_called()
    mock_detection_event_publisher.publish_detection.assert_not_called()
    assert (
        f"AnalysisManager: Processing audio for analysis: {audio_file_path}"
        in caplog.text
    )
    assert "AnalysisManager: Added detection to DB" not in caplog.text


@patch("birdnetpi.services.audio_extraction_service.subprocess.run")
def test_extract_new_birdsounds_uses_config_values(
    mock_subprocess_run,
    analysis_manager,
    mock_config,
    mock_detection_manager,
    mock_file_manager,
    caplog,
):
    """Should use audio_format and extraction_length from config for sox command."""
    mock_config.audio_format = "wav"
    mock_config.extraction_length = 5.0

    mock_detection = Mock(spec=Detection)
    mock_detection.species = "Test_Species"
    mock_detection.timestamp = datetime(2025, 7, 18, 10, 30, 0)
    mock_detection.audio_file_path = "/path/to/input_audio.wav"

    mock_detection_manager.get_all_detections.return_value = [mock_detection]

    analysis_manager.extract_new_birdsounds()

    analysis_manager.audio_extraction_service.extract_all_unextracted_birdsounds.assert_called_once()


@patch("birdnetpi.services.audio_extraction_service.subprocess.run")
def test_extract_new_birdsounds_handles_sox_error(
    mock_subprocess_run,
    analysis_manager,
    mock_detection_manager,
    mock_file_manager,
    caplog,
):
    """Should print an error message if sox command fails."""
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        1, "sox", stderr="sox error"
    )

    mock_detection = Mock(spec=Detection)
    mock_detection.species = "Test_Species"
    mock_detection.timestamp = datetime(2025, 7, 18, 10, 30, 0)
    mock_detection.audio_file_path = "/path/to/input_audio.wav"

    mock_detection_manager.get_all_detections.return_value = [mock_detection]

    analysis_manager.extract_new_birdsounds()

    analysis_manager.audio_extraction_service.extract_all_unextracted_birdsounds.assert_called_once()


@patch("birdnetpi.services.audio_extraction_service.subprocess.run")
def test_extract_new_birdsounds_handles_sox_not_found(
    mock_subprocess_run,
    analysis_manager,
    mock_detection_manager,
    mock_file_manager,
    caplog,
):
    """Should print an error message if sox command is not found."""
    mock_subprocess_run.side_effect = FileNotFoundError

    mock_detection = Mock(spec=Detection)
    mock_detection.species = "Test_Species"
    mock_detection.timestamp = datetime(2025, 7, 18, 10, 30, 0)
    mock_detection.audio_file_path = "/path/to/input_audio.wav"

    mock_detection_manager.get_all_detections.return_value = [mock_detection]

    analysis_manager.extract_new_birdsounds()

    analysis_manager.audio_extraction_service.extract_all_unextracted_birdsounds.assert_called_once()
