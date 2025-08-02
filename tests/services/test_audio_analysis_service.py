import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.audio_analysis_service import AudioAnalysisService
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.file_path_resolver import FilePathResolver


@pytest.fixture
def mock_file_manager():
    """Return a mock FileManager instance."""
    mock = MagicMock(spec=FileManager)
    mock.save_detection_audio.return_value = MagicMock(
        file_path="/mock/path/audio.wav",
        duration=10.0,
        size_bytes=1000,
        recording_start_time=datetime.now(),
    )
    return mock


@pytest.fixture
def mock_file_path_resolver():
    """Return a mock FilePathResolver instance."""
    mock = MagicMock(spec=FilePathResolver)
    mock.get_detection_audio_path.return_value = "/mock/path/audio.wav"
    return mock


@pytest.fixture
def mock_config():
    """Return a mock BirdNETConfig instance."""
    mock = MagicMock(spec=BirdNETConfig)
    mock.sample_rate = 48000
    mock.audio_channels = 1
    mock.latitude = 40.7128
    mock.longitude = -74.0060
    mock.sensitivity = 1.25
    mock.confidence = 0.7
    return mock


@pytest.fixture
@patch("birdnetpi.services.audio_analysis_service.AnalysisClientService")
def audio_analysis_service(
    mock_analysis_client_class, mock_file_manager, mock_file_path_resolver, mock_config
):
    """Return an AudioAnalysisService instance with mocked dependencies."""
    # Mock the AnalysisClientService constructor to avoid model loading
    mock_analysis_client = MagicMock()
    mock_analysis_client_class.return_value = mock_analysis_client

    service = AudioAnalysisService(
        mock_file_manager, mock_file_path_resolver, mock_config, audio_websocket_service=None
    )
    service.analysis_client = mock_analysis_client
    return service


@pytest.fixture(autouse=True)
def caplog_for_audio_analysis_service(caplog):
    """Fixture to capture logs from audio_analysis_service.py."""
    caplog.set_level(logging.INFO, logger="birdnetpi.services.audio_analysis_service")
    yield


class TestAudioAnalysisService:
    """Test the AudioAnalysisService class."""

    async def test_init(
        self, audio_analysis_service, mock_file_manager, mock_file_path_resolver, mock_config
    ):
        """Should initialize with correct dependencies and attributes."""
        assert audio_analysis_service.file_manager == mock_file_manager
        assert audio_analysis_service.file_path_resolver == mock_file_path_resolver
        assert audio_analysis_service.config == mock_config
        assert hasattr(audio_analysis_service, "analysis_client")
        assert hasattr(audio_analysis_service, "audio_buffer")

    @pytest.mark.asyncio
    async def test_process_audio_chunk_accumulates_buffer(self, audio_analysis_service):
        """Should accumulate audio data in buffer."""
        initial_buffer_length = len(audio_analysis_service.audio_buffer)
        audio_data = b"\x00\x01\x02\x03"
        await audio_analysis_service.process_audio_chunk(audio_data)
        assert len(audio_analysis_service.audio_buffer) > initial_buffer_length

    @pytest.mark.asyncio
    @patch(
        "birdnetpi.services.audio_analysis_service.AudioAnalysisService._analyze_audio_chunk",
        new_callable=AsyncMock,
    )
    async def test_process_audio_chunk_calls_analyze_when_buffer_full(
        self, mock_analyze_audio_chunk, audio_analysis_service
    ):
        """Should call _analyze_audio_chunk when buffer has enough data."""
        # Mock config for known sample rate
        audio_analysis_service.config.sample_rate = 48000
        audio_analysis_service.buffer_size_samples = 48000 * 3  # 3 seconds

        # Create enough audio data to trigger analysis
        chunk_size = 1024
        audio_chunk = np.zeros(chunk_size, dtype=np.int16).tobytes()

        # Feed chunks until buffer is full
        chunks_needed = (audio_analysis_service.buffer_size_samples // chunk_size) + 1
        for _ in range(chunks_needed):
            await audio_analysis_service.process_audio_chunk(audio_chunk)

        # Should have called analyze at least once when buffer was full
        assert mock_analyze_audio_chunk.call_count >= 1

    @pytest.mark.asyncio
    @patch(
        "birdnetpi.services.audio_analysis_service.AudioAnalysisService._send_detection_event",
        new_callable=AsyncMock,
    )
    async def test_analyze_audio_chunk_with_detections(
        self, mock_send_detection_event, audio_analysis_service
    ):
        """Should send detection events for confident detections."""
        # Mock the analysis client to return some detections
        audio_analysis_service.analysis_client.get_analysis_results.return_value = [
            ("Robin", 0.85),
            ("Crow", 0.72),
            ("Human", 0.65),  # Below confidence threshold
        ]

        # Create a mock audio chunk
        audio_chunk = np.zeros(48000 * 3, dtype=np.float32)  # 3 seconds of silence

        await audio_analysis_service._analyze_audio_chunk(audio_chunk)

        # Should have called send_detection_event twice (for Robin and Crow, not Human)
        assert mock_send_detection_event.call_count == 2

        # Check the calls
        calls = mock_send_detection_event.call_args_list
        assert calls[0][0][0] == "Robin"  # species
        assert calls[0][0][1] == 0.85  # confidence
        assert calls[1][0][0] == "Crow"  # species
        assert calls[1][0][1] == 0.72  # confidence

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_success(
        self,
        mock_async_client,
        audio_analysis_service,
        mock_file_manager,
        mock_file_path_resolver,
        mock_config,
        caplog,
    ):
        """Should successfully send a detection event and log info."""
        mock_post = AsyncMock(return_value=MagicMock(status_code=201))
        mock_async_client.return_value.__aenter__.return_value.post = mock_post

        species = "Test Species"
        confidence = 0.8
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(species, confidence, raw_audio_bytes)

        mock_file_path_resolver.get_detection_audio_path.assert_called_once()
        mock_file_manager.save_detection_audio.assert_called_once()
        mock_async_client.assert_called_once()
        mock_post.assert_called_once()
        assert "Detection event sent" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_audio_save_failure(
        self, mock_async_client, audio_analysis_service, mock_file_manager, caplog
    ):
        """Should log an error and not send HTTP request if audio save fails."""
        mock_file_manager.save_detection_audio.side_effect = Exception("Audio save error")

        species = "Test Species"
        confidence = 0.8
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(species, confidence, raw_audio_bytes)

        mock_async_client.assert_not_called()
        assert "Failed to save detection audio: Audio save error" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_httpx_request_error(
        self, mock_async_client, audio_analysis_service, caplog
    ):
        """Should log an error if httpx.RequestError occurs."""
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = (
            httpx.RequestError(
                "Network error",
                request=httpx.Request("POST", "http://test.com"),
            )
        )

        species = "Test Species"
        confidence = 0.8
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(species, confidence, raw_audio_bytes)

        assert "Error sending detection event: Network error" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_httpx_status_error(
        self, mock_async_client, audio_analysis_service, caplog
    ):
        """Should log an error if httpx.HTTPStatusError occurs."""
        mock_response = MagicMock(status_code=404, text="Not Found")
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = (
            httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        )

        species = "Test Species"
        confidence = 0.8
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(species, confidence, raw_audio_bytes)

        assert "Error response 404 while sending detection event: Not Found" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_generic_exception(
        self, mock_async_client, audio_analysis_service, caplog
    ):
        """Should log a generic error if an unexpected exception occurs."""
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = Exception(
            "Unexpected error"
        )

        species = "Test Species"
        confidence = 0.8
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(species, confidence, raw_audio_bytes)

        assert (
            "An unexpected error occurred while sending detection event: Unexpected error"
            in caplog.text
        )
