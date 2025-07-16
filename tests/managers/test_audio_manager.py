from unittest.mock import Mock

import pytest

from birdnetpi.managers.audio_manager import AudioManager
from birdnetpi.models.livestream_config import LivestreamConfig
from birdnetpi.services.file_manager import FileManager


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    return Mock(spec=FileManager)


@pytest.fixture
def audio_manager(mock_file_manager):
    """Provide an AudioManager instance with a mocked FileManager."""
    return AudioManager(file_manager=mock_file_manager)


def test_custom_record(audio_manager, capsys):
    """Should print a message indicating audio recording"""
    duration = 10
    output_path = "/path/to/recording.wav"
    audio_manager.custom_record(duration, output_path)
    captured = capsys.readouterr()
    assert f"Recording audio for {duration} seconds to {output_path}" in captured.out


def test_livestream(audio_manager, capsys):
    """Should print a message indicating livestreaming"""
    config = LivestreamConfig(
        input_device="hw:0,0", output_url="rtsp://localhost:8554/live.stream"
    )
    audio_manager.livestream(config)
    captured = capsys.readouterr()
    assert (
        f"Starting livestream from {config.input_device} to {config.output_url}"
        in captured.out
    )
