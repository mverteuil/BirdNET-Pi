import os  # Import os for mocking
from unittest.mock import Mock, patch

import pytest

from birdnetpi.managers.audio_manager import AudioManager
from birdnetpi.models.birdnet_config import BirdNETConfig  # Added import
from birdnetpi.models.livestream_config import LivestreamConfig
from birdnetpi.services.file_manager import FileManager


@pytest.fixture
def mock_file_manager():
    """Provide a mock FileManager instance."""
    return Mock(spec=FileManager)


@pytest.fixture
def mock_config():  # Added mock_config fixture
    """Provide a mock BirdNETConfig instance."""
    mock = Mock(spec=BirdNETConfig)
    # Add any necessary attributes that AudioManager might access from config
    # For now, assuming default values are fine or not accessed by these tests
    return mock


@pytest.fixture
def audio_manager(mock_file_manager, mock_config):  # Added mock_config dependency
    """Provide an AudioManager instance with a mocked FileManager and Config."""
    return AudioManager(
        file_manager=mock_file_manager, config=mock_config
    )  # Pass config


@patch("birdnetpi.managers.audio_manager.os.makedirs")
@patch("birdnetpi.managers.audio_manager.subprocess.run")
def test_custom_record(mock_subprocess_run, mock_makedirs, audio_manager, capsys):
    """Should print a message indicating audio recording and call os.makedirs and subprocess.run."""
    duration = 10
    output_path = "/path/to/recording.wav"

    # Mock the return value of subprocess.run for custom_record
    mock_subprocess_run.return_value = Mock(returncode=0, stdout="", stderr="")

    audio_manager.custom_record(duration, output_path)
    captured = capsys.readouterr()
    assert f"Recording audio for {duration} seconds to {output_path}" in captured.out
    mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
    mock_subprocess_run.assert_called_once_with(
        [
            "arecord",
            "-d",
            str(duration),
            "-f",
            "S16_LE",
            "-r",
            "44100",
            "-c",
            "1",
            output_path,
        ],
        check=True,  # Raise CalledProcessError if the command returns a non-zero exit code
        capture_output=True,  # Capture stdout and stderr
    )


@patch("birdnetpi.managers.audio_manager.subprocess.run")
def test_livestream(mock_subprocess_run, audio_manager, capsys):
    """Should print a message indicating livestreaming and call subprocess.run."""
    config = LivestreamConfig(
        input_device="hw:0,0", output_url="rtsp://localhost:8554/live.stream"
    )
    # Mock the return value of subprocess.run for livestream
    mock_subprocess_run.return_value = Mock(returncode=0, stdout="", stderr="")

    audio_manager.livestream(config)
    captured = capsys.readouterr()
    assert (
        f"Starting livestream from {config.input_device} to {config.output_url}"
        in captured.out
    )
    mock_subprocess_run.assert_called_once_with(
        [
            "ffmpeg",
            "-f",
            "alsa",
            "-i",
            config.input_device,
            "-f",
            "rtsp",
            config.output_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
