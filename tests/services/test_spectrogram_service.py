"""Tests for the SpectrogramService."""

import logging
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from birdnetpi.services.spectrogram_service import SpectrogramService


@pytest.fixture
def spectrogram_service():
    """Create a SpectrogramService instance for testing."""
    return SpectrogramService(
        sample_rate=48000,
        channels=1,
        window_size=512,  # Smaller for faster tests
        overlap=0.5,  # Simpler for testing
        update_rate=10.0,  # Lower rate for testing
    )


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    mock = MagicMock()
    mock.send_json = AsyncMock()
    return mock


class TestSpectrogramService:
    """Test the SpectrogramService class."""

    def test_initialization(self, spectrogram_service):
        """Test that SpectrogramService initializes correctly."""
        service = spectrogram_service

        assert service.sample_rate == 48000
        assert service.channels == 1
        assert service.window_size == 512
        assert service.overlap == 0.5
        assert service.update_rate == 10.0

        # Check derived parameters
        assert service.hop_length == 256  # window_size * (1 - overlap)
        assert service.samples_per_update == 4800  # sample_rate / update_rate

        # Check initial state
        assert len(service.audio_buffer) == 0
        assert len(service.connected_websockets) == 0
        assert len(service.freq_bins) == 256  # window_size // 2

    @pytest.mark.asyncio
    async def test_websocket_connection(self, spectrogram_service, mock_websocket):
        """Test WebSocket connection and disconnection."""
        service = spectrogram_service

        # Test connection
        await service.connect_websocket(mock_websocket)
        assert mock_websocket in service.connected_websockets
        assert len(service.connected_websockets) == 1

        # Verify config was sent
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "config"
        assert call_args["sample_rate"] == 48000
        assert call_args["window_size"] == 512

        # Test disconnection
        await service.disconnect_websocket(mock_websocket)
        assert mock_websocket not in service.connected_websockets
        assert len(service.connected_websockets) == 0

    @pytest.mark.asyncio
    async def test_process_audio_chunk_no_clients(self, spectrogram_service):
        """Test that processing returns early when no clients are connected."""
        service = spectrogram_service

        # Create test audio data
        audio_samples = np.zeros(1000, dtype=np.int16)
        audio_bytes = audio_samples.tobytes()

        # Process should return immediately with no clients
        await service.process_audio_chunk(audio_bytes)

        # Buffer should still be empty since no processing occurred
        assert len(service.audio_buffer) == 0

    @pytest.mark.asyncio
    async def test_process_audio_chunk_with_client(self, spectrogram_service, mock_websocket):
        """Test audio processing with connected client."""
        service = spectrogram_service
        await service.connect_websocket(mock_websocket)

        # Create test audio data (not enough to trigger spectrogram generation)
        audio_samples = np.zeros(1000, dtype=np.int16)
        audio_bytes = audio_samples.tobytes()

        await service.process_audio_chunk(audio_bytes)

        # Buffer should contain the audio data
        assert len(service.audio_buffer) == 1000

    @pytest.mark.asyncio
    async def test_spectrogram_generation(self, spectrogram_service, mock_websocket):
        """Test spectrogram generation and transmission."""
        service = spectrogram_service
        await service.connect_websocket(mock_websocket)

        # Reset the mock to ignore the config message
        mock_websocket.send_json.reset_mock()

        # Create enough audio data to trigger spectrogram generation
        # Generate a sine wave for more interesting spectrogram
        t = np.linspace(0, 1, service.samples_per_update, False)
        sine_wave = np.sin(2 * np.pi * 1000 * t)  # 1kHz tone
        audio_samples = (sine_wave * 16384).astype(np.int16)  # Convert to int16
        audio_bytes = audio_samples.tobytes()

        await service.process_audio_chunk(audio_bytes)

        # Should have triggered spectrogram generation and sent data
        assert mock_websocket.send_json.called

        # Check the sent data
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "spectrogram"
        assert "data" in call_args
        assert "timestamp" in call_args
        assert "shape" in call_args

        # Verify the data is a list (serializable)
        assert isinstance(call_args["data"], list)

    @pytest.mark.asyncio
    async def test_multi_channel_audio(self):
        """Test handling of multi-channel audio."""
        service = SpectrogramService(
            sample_rate=48000,
            channels=2,  # Stereo
            window_size=512,
            overlap=0.5,
            update_rate=10.0,
        )

        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock()
        await service.connect_websocket(mock_ws)
        mock_ws.send_json.reset_mock()

        # Create stereo audio data (interleaved L/R)
        samples_per_channel = 1000
        left_channel = np.sin(2 * np.pi * 1000 * np.linspace(0, 1, samples_per_channel))
        right_channel = np.sin(2 * np.pi * 2000 * np.linspace(0, 1, samples_per_channel))

        # Interleave channels
        stereo_samples = np.zeros(samples_per_channel * 2, dtype=np.float32)
        stereo_samples[0::2] = left_channel  # Left channel
        stereo_samples[1::2] = right_channel  # Right channel

        # Convert to int16
        stereo_int16 = (stereo_samples * 16384).astype(np.int16)
        audio_bytes = stereo_int16.tobytes()

        await service.process_audio_chunk(audio_bytes)

        # Check that only the first channel was used (buffer length should be samples_per_channel)
        assert len(service.audio_buffer) == samples_per_channel

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, spectrogram_service):
        """Test error handling when WebSocket send fails."""
        service = spectrogram_service

        # Create a mock WebSocket that raises an exception
        failing_websocket = MagicMock()
        failing_websocket.send_json = AsyncMock(side_effect=Exception("Connection failed"))

        await service.connect_websocket(failing_websocket)

        # The websocket should be disconnected after the error
        # (We need to trigger the spectrogram generation to test this)

        # Create enough audio data to trigger spectrogram generation
        t = np.linspace(0, 1, service.samples_per_update, False)
        sine_wave = np.sin(2 * np.pi * 1000 * t)
        audio_samples = (sine_wave * 16384).astype(np.int16)
        audio_bytes = audio_samples.tobytes()

        await service.process_audio_chunk(audio_bytes)

        # The failing websocket should have been removed from connected clients
        assert failing_websocket not in service.connected_websockets

    def test_get_parameters(self, spectrogram_service):
        """Test parameter retrieval."""
        service = spectrogram_service

        params = service.get_parameters()

        expected_params = {
            "sample_rate": 48000,
            "channels": 1,
            "window_size": 512,
            "overlap": 0.5,
            "update_rate": 10.0,
            "hop_length": 256,
            "freq_range": [0, 24000],  # sample_rate // 2
            "connected_clients": 0,
        }

        assert params == expected_params

    @pytest.mark.asyncio
    async def test_buffer_management(self, spectrogram_service, mock_websocket):
        """Test that audio buffer is properly managed."""
        service = spectrogram_service
        await service.connect_websocket(mock_websocket)

        # Send multiple small chunks
        for _ in range(3):
            audio_samples = np.zeros(1000, dtype=np.int16)
            audio_bytes = audio_samples.tobytes()
            await service.process_audio_chunk(audio_bytes)

        # Buffer should accumulate data
        assert len(service.audio_buffer) == 3000

        # Now send enough data to trigger spectrogram generation
        remaining_samples = service.samples_per_update - len(service.audio_buffer)
        audio_samples = np.zeros(remaining_samples + 100, dtype=np.int16)  # Extra samples
        audio_bytes = audio_samples.tobytes()

        await service.process_audio_chunk(audio_bytes)

        # Buffer should be reduced (keeping some overlap)
        overlap_samples = int(service.samples_per_update * 0.25)
        assert len(service.audio_buffer) == overlap_samples

    def test_frequency_bins_calculation(self):
        """Test that frequency bins are calculated correctly."""
        service = SpectrogramService(sample_rate=48000, channels=1, window_size=1024)

        # Frequency bins should go from 0 to Nyquist frequency
        expected_bins = np.fft.fftfreq(1024, 1 / 48000)[:512]  # First half only

        np.testing.assert_array_almost_equal(service.freq_bins, expected_bins)

        # Check some specific values
        assert service.freq_bins[0] == 0  # DC component
        # The last frequency bin should be close to (but not exactly) Nyquist
        nyquist = 48000 / 2
        assert service.freq_bins[-1] < nyquist  # Should be less than Nyquist

    @pytest.mark.asyncio
    async def test_spectrogram_generation_error_handling(
        self, spectrogram_service, mock_websocket, caplog
    ):
        """Test error handling during spectrogram generation."""
        service = spectrogram_service
        await service.connect_websocket(mock_websocket)
        mock_websocket.send_json.reset_mock()

        # First, add enough audio data to the buffer
        t = np.linspace(0, 1, service.samples_per_update, False)
        sine_wave = np.sin(2 * np.pi * 1000 * t)
        audio_samples = (sine_wave * 16384).astype(np.int16)
        audio_bytes = audio_samples.tobytes()

        # Process the audio to fill the buffer
        await service.process_audio_chunk(audio_bytes)

        # Now mock scipy.signal.spectrogram to raise an exception
        from unittest.mock import patch

        with patch(
            "scipy.signal.spectrogram", side_effect=Exception("Spectrogram processing error")
        ):
            # Create more audio data to trigger another spectrogram generation
            await service.process_audio_chunk(audio_bytes)

            # Should have logged the error from the outer exception handler
            assert any(
                "Error generating spectrogram" in record.message
                for record in caplog.records
                if record.levelname == "ERROR"
            )


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """Set up logging for tests."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.services.spectrogram_service")
