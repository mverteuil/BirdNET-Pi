from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pytest
import subprocess
from pathlib import Path

from birdnetpi.managers.analysis_manager import AnalysisManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig, DataConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    mock.audio_format = "mp3"
    mock.extraction_length = 6.0
    mock.data = Mock(spec=DataConfig) # Mock the data attribute as a DataConfig instance
    mock.data.extracted_dir = "/tmp/extracted"
    return mock


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    mock = Mock(spec=FileManager)
    
    # Create a mock Path object that has a mkdir method and supports / operator
    mock_extracted_path = MagicMock(spec=Path)
    mock_extracted_path.mkdir.return_value = None
    # Set the name attribute for the __truediv__ side_effect
    mock_extracted_path.name = "extracted_dir_mock" 
    mock_extracted_path.__truediv__.side_effect = lambda other: Path(str(mock_extracted_path.name)) / other

    # Configure side_effect for get_full_path to return different mocks/values
    # based on the argument. This is crucial for the mkdir assertion.
    def get_full_path_side_effect(path_arg):
        if path_arg == "/tmp/extracted":
            return mock_extracted_path
        else:
            return path_arg # For audio_file_path, return as string

    mock.get_full_path.side_effect = get_full_path_side_effect
    mock.mock_extracted_path = mock_extracted_path # Store for assertion
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
def mock_detection_event_publisher():
    """Provide a mock DetectionEventPublisher instance."""
    return Mock(spec=DetectionEventPublisher)


@pytest.fixture
def analysis_manager(
    mock_config,
    mock_file_manager,
    mock_detection_manager,
    mock_analysis_client_service,
    mock_detection_event_publisher,
):
    """Provide an AnalysisManager instance with mocked dependencies."""
    return AnalysisManager(
        config=mock_config,
        file_manager=mock_file_manager,
        detection_manager=mock_detection_manager,
        analysis_client_service=mock_analysis_client_service,
        detection_event_publisher=mock_detection_event_publisher,
    )


def test_process_audio_for_analysis_with_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_detection_manager,
    mock_detection_event_publisher,
    capsys,
):
    """Should process audio, add detection, and publish event when analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    # Corrected mock for analysis_results
    mock_analysis_client_service.analyze_audio.return_value = [
        {"species": "Test Species", "confidence": 0.9, "timestamp": "2025-07-18T10:30:00"}
    ]
    mock_detection_manager.add_detection.return_value = Mock(species="Test Species")

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_analysis_client_service.analyze_audio.assert_called_once_with(audio_file_path)
    mock_detection_manager.add_detection.assert_called_once()
    mock_detection_event_publisher.publish_detection.assert_called_once()
    captured = capsys.readouterr()
    assert f"Processing audio for analysis: {audio_file_path}" in captured.out
    assert "Added detection to DB: Test Species" in captured.out


def test_process_audio_for_analysis_no_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_detection_manager,
    mock_detection_event_publisher,
    capsys,
):
    """Should only analyze audio when no analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    mock_analysis_client_service.analyze_audio.return_value = [] # Empty list for no results

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_analysis_client_service.analyze_audio.assert_called_once_with(audio_file_path)
    mock_detection_manager.add_detection.assert_not_called()
    mock_detection_event_publisher.publish_detection.assert_not_called()
    captured = capsys.readouterr()
    assert f"Processing audio for analysis: {audio_file_path}" in captured.out
    assert "Added detection to DB" not in captured.out


@patch("birdnetpi.managers.analysis_manager.subprocess.run")
def test_extract_new_birdsounds_uses_config_values(
    mock_subprocess_run, analysis_manager, mock_config, mock_detection_manager, mock_file_manager, capsys
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

    # get_full_path is called twice: once for extracted_dir, once for audio_file_path
    mock_file_manager.get_full_path.assert_any_call(mock_config.data.extracted_dir)
    mock_file_manager.get_full_path.assert_any_call(mock_detection.audio_file_path)
    # Ensure mkdir was called on the mock object returned by get_full_path
    mock_file_manager.mock_extracted_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    expected_output_filename = f"{mock_detection.species}_{mock_detection.timestamp.strftime('%Y%m%d_%H%M%S')}.{mock_config.audio_format}"
    # The mock_file_manager.get_full_path.return_value is the mock_path_object
    expected_output_filepath = mock_file_manager.mock_extracted_path / expected_output_filename

    mock_subprocess_run.assert_called_once_with(
        [
            "sox",
            str(mock_detection.audio_file_path),
            str(expected_output_filepath),
            "trim",
            str(mock_detection.timestamp.hour * 3600 + mock_detection.timestamp.minute * 60 + mock_detection.timestamp.second),
            str(mock_config.extraction_length),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    captured = capsys.readouterr()
    assert "Extracting new birdsounds..." in captured.out
    assert f"Extracted {mock_detection.species} to {expected_output_filepath}" in captured.out

@patch("birdnetpi.managers.analysis_manager.subprocess.run")
def test_extract_new_birdsounds_handles_sox_error(
    mock_subprocess_run, analysis_manager, mock_detection_manager, mock_file_manager, capsys
):
    """Should print an error message if sox command fails."""
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(1, "sox", stderr="sox error")

    mock_detection = Mock(spec=Detection)
    mock_detection.species = "Test_Species"
    mock_detection.timestamp = datetime(2025, 7, 18, 10, 30, 0)
    mock_detection.audio_file_path = "/path/to/input_audio.wav"

    mock_detection_manager.get_all_detections.return_value = [mock_detection]

    analysis_manager.extract_new_birdsounds()

    captured = capsys.readouterr()
    assert "Error extracting audio for Test_Species: sox error" in captured.err

@patch("birdnetpi.managers.analysis_manager.subprocess.run")
def test_extract_new_birdsounds_handles_sox_not_found(
    mock_subprocess_run, analysis_manager, mock_detection_manager, mock_file_manager, capsys
):
    """Should print an error message if sox command is not found."""
    mock_subprocess_run.side_effect = FileNotFoundError

    mock_detection = Mock(spec=Detection)
    mock_detection.species = "Test_Species"
    mock_detection.timestamp = datetime(2025, 7, 18, 10, 30, 0)
    mock_detection.audio_file_path = "/path/to/input_audio.wav"

    mock_detection_manager.get_all_detections.return_value = [mock_detection]

    analysis_manager.extract_new_birdsounds()

    captured = capsys.readouterr()
    assert "Error: sox command not found. Please ensure it's installed and in your PATH." in captured.err
