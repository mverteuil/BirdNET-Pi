from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.services.audio_extraction_service import AudioExtractionService


@pytest.fixture
def mock_config():
    """Provide a mock BirdNETConfig instance."""
    return MagicMock()


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    return MagicMock()


@pytest.fixture
def mock_detection_manager():
    """Provide a mock DetectionManager instance."""
    return MagicMock()


@pytest.fixture
def audio_extraction_service(mock_config, mock_file_manager, mock_detection_manager):
    """Provide an AudioExtractionService instance with mocked dependencies."""
    return AudioExtractionService(
        config=mock_config,
        file_manager=mock_file_manager,
        detection_manager=mock_detection_manager,
    )


def test_extract_birdsounds_for_detection(audio_extraction_service):
    """Should extract birdsounds for a given detection ID."""
    with (
        patch.object(
            audio_extraction_service.detection_manager, "get_detection_by_id"
        ) as mock_get_detection_by_id,
        patch.object(
            audio_extraction_service.detection_manager, "get_audio_file_by_path"
        ) as mock_get_audio_file_by_path,
        patch("subprocess.run") as mock_run,
    ):
        mock_get_detection_by_id.return_value = MagicMock()
        mock_get_audio_file_by_path.return_value = MagicMock()
        audio_extraction_service.extract_birdsounds_for_detection(1)
        mock_run.assert_called_once()


def test_extract_all_unextracted_birdsounds(audio_extraction_service):
    """Should extract all unextracted birdsounds."""
    with (
        patch.object(
            audio_extraction_service.detection_manager, "get_all_detections"
        ) as mock_get_all_detections,
        patch.object(
            audio_extraction_service, "extract_birdsounds_for_detection"
        ) as mock_extract_birdsounds_for_detection,
    ):
        mock_get_all_detections.return_value = [MagicMock()]
        audio_extraction_service.extract_all_unextracted_birdsounds()
        mock_extract_birdsounds_for_detection.assert_called_once()
