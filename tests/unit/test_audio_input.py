import pytest
import sounddevice as sd
import numpy as np
from unittest.mock import MagicMock, patch

from birdnetpi.utils.audio_input import AudioInput

@pytest.fixture
def mock_sounddevice_stream():
    with patch('sounddevice.InputStream') as mock_stream_class:
        mock_stream_instance = MagicMock()
        mock_stream_class.return_value = mock_stream_instance
        yield mock_stream_instance

def test_audio_input_init():
    audio_input = AudioInput(samplerate=44100, channels=1, blocksize=1024)
    assert audio_input.samplerate == 44100
    assert audio_input.channels == 1
    assert audio_input.blocksize == 1024
    assert audio_input.stream is None

def test_audio_input_start_stream(mock_sounddevice_stream):
    audio_input = AudioInput(samplerate=44100, channels=1, blocksize=1024)
    audio_input.start_stream()
    mock_sounddevice_stream.start.assert_called_once()
    assert audio_input.stream is not None

def test_audio_input_read_block(mock_sounddevice_stream):
    audio_input = AudioInput(samplerate=44100, channels=1, blocksize=1024)
    audio_input.start_stream()
    
    # Mock the read method to return some dummy data
    mock_sounddevice_stream.read.return_value = (np.zeros((1024, 1)), False)
    
    data = audio_input.read_block()
    mock_sounddevice_stream.read.assert_called_once_with(1024)
    assert isinstance(data, np.ndarray)

def test_audio_input_stop_stream(mock_sounddevice_stream):
    audio_input = AudioInput(samplerate=44100, channels=1, blocksize=1024)
    audio_input.start_stream()
    audio_input.stop_stream()
    mock_sounddevice_stream.stop.assert_called_once()
    mock_sounddevice_stream.close.assert_called_once()
    assert audio_input.stream is None

def test_audio_input_context_manager(mock_sounddevice_stream):
    with AudioInput(samplerate=44100, channels=1, blocksize=1024) as audio_input:
        mock_sounddevice_stream.start.assert_called_once()
        assert audio_input.stream is not None
    mock_sounddevice_stream.stop.assert_called_once()
    mock_sounddevice_stream.close.assert_called_once()
    assert audio_input.stream is None
