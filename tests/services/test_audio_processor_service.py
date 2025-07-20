from unittest.mock import patch

import numpy as np
import pytest

from birdnetpi.services.audio_processor_service import AudioProcessorService


@pytest.fixture
def audio_processor_service():
    """Provide an AudioProcessorService instance for testing."""
    return AudioProcessorService()


def test_split_signal(audio_processor_service):
    """Should split a signal into chunks."""
    sig = np.zeros(48000 * 10)  # 10 seconds of audio
    chunks = audio_processor_service._split_signal(sig, 48000, 0.5)
    assert len(chunks) == 4


def test_read_audio_data(audio_processor_service):
    """Should read audio data and return a list of chunks."""
    with patch("librosa.load") as mock_load:
        mock_load.return_value = (np.zeros(48000 * 10), 48000)
        chunks = audio_processor_service.read_audio_data("test.wav", 0.5)
        assert len(chunks) == 4
