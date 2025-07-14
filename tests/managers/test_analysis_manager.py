from unittest.mock import Mock

import pytest

from managers.analysis_manager import AnalysisManager
from managers.database_manager import DatabaseManager
from models.birdnet_config import BirdNETConfig
from services.analysis_client_service import AnalysisClientService
from services.detection_event_publisher import DetectionEventPublisher
from services.file_manager import FileManager


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    return Mock(spec=BirdNETConfig)


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    return Mock(spec=FileManager)


@pytest.fixture
def mock_database_manager():
    """Provide a mock DatabaseManager instance."""
    return Mock(spec=DatabaseManager)


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
    mock_database_manager,
    mock_analysis_client_service,
    mock_detection_event_publisher,
):
    """Provide an AnalysisManager instance with mocked dependencies."""
    return AnalysisManager(
        config=mock_config,
        file_manager=mock_file_manager,
        database_manager=mock_database_manager,
        analysis_client_service=mock_analysis_client_service,
        detection_event_publisher=mock_detection_event_publisher,
    )


def test_process_audio_for_analysis_with_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_database_manager,
    mock_detection_event_publisher,
    capsys,
):
    """Should process audio, add detection, and publish event when analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    mock_analysis_client_service.analyze_audio.return_value = {"some": "results"}
    mock_database_manager.add_detection.return_value = Mock(species="Test Species")

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_analysis_client_service.analyze_audio.assert_called_once_with(audio_file_path)
    mock_database_manager.add_detection.assert_called_once()
    mock_detection_event_publisher.publish_detection.assert_called_once()
    captured = capsys.readouterr()
    assert f"Processing audio for analysis: {audio_file_path}" in captured.out
    assert "Added detection to DB: Test Species" in captured.out


def test_process_audio_for_analysis_no_results(
    analysis_manager,
    mock_analysis_client_service,
    mock_database_manager,
    mock_detection_event_publisher,
    capsys,
):
    """Should only analyze audio when no analysis results are present"""
    audio_file_path = "/path/to/audio.wav"
    mock_analysis_client_service.analyze_audio.return_value = {}

    analysis_manager.process_audio_for_analysis(audio_file_path)

    mock_analysis_client_service.analyze_audio.assert_called_once_with(audio_file_path)
    mock_database_manager.add_detection.assert_not_called()
    mock_detection_event_publisher.publish_detection.assert_not_called()
    captured = capsys.readouterr()
    assert f"Processing audio for analysis: {audio_file_path}" in captured.out
    assert "Added detection to DB" not in captured.out


def test_extract_new_birdsounds(analysis_manager, capsys):
    """Should print a message indicating new birdsounds extraction"""
    analysis_manager.extract_new_birdsounds()
    captured = capsys.readouterr()
    assert "Extracting new birdsounds..." in captured.out
