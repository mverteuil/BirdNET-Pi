import asyncio
import logging
import threading
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest

from birdnetpi.audio.audio_analysis_manager import AudioAnalysisManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.system.file_manager import FileManager


@pytest.fixture
def test_config_data():
    """Provide test configuration data."""
    return {
        "sample_rate": 48000,
        "audio_channels": 1,
        "latitude": 40.7128,
        "longitude": -74.0060,
        "sensitivity": 1.25,
        "species_confidence_threshold": 0.7,
        "detection_threshold": 0.7,
        "buffer_size_seconds": 3,
    }


@pytest.fixture
def test_detection_result():
    """Provide test detection result data."""
    from pathlib import Path

    # Both paths should be the same relative path
    relative_path = Path("recordings/Test_species/20240101_120000.wav")
    return {
        "file_path": relative_path,  # FileManager returns the same relative path
        "duration": 10.0,
        "size_bytes": 1000,
        "recording_start_time": datetime.now(),
        "audio_path": relative_path,  # Relative path from get_detection_audio_path
    }


@pytest.fixture
def test_audio_data():
    """Provide test audio data for analysis."""
    return {
        "chunk_size": 1024,
        "sample_rate": 48000,
        "buffer_size_samples": 48000 * 3,  # 3 seconds
        "duration_seconds": 3.0,
        "silence_chunk": np.zeros(48000 * 3, dtype=np.float32),
        "test_chunk": np.ones(48000 * 3, dtype=np.float32) * 0.1,
    }


@pytest.fixture
def mock_file_manager(test_detection_result):
    """Return a mock FileManager instance with test data."""
    mock = MagicMock(spec=FileManager)
    mock.save_detection_audio.return_value = MagicMock(
        file_path=test_detection_result["file_path"],
        duration=test_detection_result["duration"],
        size_bytes=test_detection_result["size_bytes"],
        recording_start_time=test_detection_result["recording_start_time"],
    )
    return mock


@pytest.fixture
def mock_path_resolver(path_resolver, test_detection_result):
    """Return a mock PathResolver instance with test data.

    Uses the global path_resolver fixture as a base to prevent MagicMock file creation.
    """
    # Create a Mock that returns the test path but doesn't create files
    from unittest.mock import MagicMock

    mock_method = MagicMock(return_value=test_detection_result["audio_path"])
    path_resolver.get_detection_audio_path = mock_method
    return path_resolver


@pytest.fixture
def mock_config(test_config_data):
    """Return a mock BirdNETConfig instance with test data."""
    mock = MagicMock(spec=BirdNETConfig)
    for key, value in test_config_data.items():
        setattr(mock, key, value)
    return mock


@pytest.fixture
@patch("birdnetpi.audio.audio_analysis_manager.BirdDetectionService")
def audio_analysis_service(
    mock_analysis_client_class, mock_file_manager, mock_path_resolver, mock_config
):
    """Return an AudioAnalysisManager instance with mocked dependencies."""
    # Mock the BirdDetectionService constructor to avoid model loading
    mock_analysis_client = MagicMock()
    mock_analysis_client_class.return_value = mock_analysis_client

    # Mock MultilingualDatabaseService and AsyncSession
    mock_multilingual_service = MagicMock()
    # Make get_best_common_name async and return a dict with common_name
    mock_multilingual_service.get_best_common_name = AsyncMock(
        return_value={"common_name": "Test Bird"}
    )
    mock_session = MagicMock()

    # Initialize SpeciesParser with the mock service
    from birdnetpi.species.parser import SpeciesParser

    SpeciesParser._instance = None  # Reset singleton
    SpeciesParser(mock_multilingual_service)  # Initialize with mock

    service = AudioAnalysisManager(
        mock_file_manager,
        mock_path_resolver,
        mock_config,
        mock_multilingual_service,
        mock_session,
        detection_buffer_max_size=100,  # Smaller buffer for testing
        buffer_flush_interval=0.1,  # Faster interval for testing
    )
    service.analysis_client = mock_analysis_client
    return service


@pytest.fixture
def test_species_data():
    """Provide test species detection data."""
    return {
        "confident": [
            ("Turdus migratorius_American Robin", 0.85),
            ("Corvus brachyrhynchos_American Crow", 0.75),
            ("Passer domesticus_House Sparrow", 0.80),
        ],
        "low_confidence": [("Homo sapiens_Human", 0.65), ("Unknown species_Unknown", 0.45)],
        "mixed": [
            ("Turdus migratorius_American Robin", 0.85),
            ("Homo sapiens_Human", 0.65),  # Below threshold
            ("Corvus brachyrhynchos_American Crow", 0.72),
        ],
    }


@pytest.fixture
def mock_detection_data(test_config_data, test_detection_result):
    """Return mock detection data for testing."""
    return {
        "species": "Test Species",
        "confidence": 0.8,
        "timestamp": datetime.now().isoformat(),
        "audio_file_path": test_detection_result["file_path"],
        "duration": test_detection_result["duration"],
        "size_bytes": test_detection_result["size_bytes"],
        "spectrogram_path": None,
        "latitude": test_config_data["latitude"],
        "longitude": test_config_data["longitude"],
        "species_confidence_threshold": test_config_data["species_confidence_threshold"],
        "week": 1,
        "sensitivity_setting": test_config_data["sensitivity"],
        "overlap": 0.5,
    }


@pytest.fixture(autouse=True)
def caplog_for_audio_analysis_service(caplog):
    """Fixture to capture logs from audio_analysis_service.py."""
    caplog.set_level(logging.INFO, logger="birdnetpi.audio.audio_analysis_manager")
    yield


class TestAudioAnalysisManager:
    """Test the AudioAnalysisManager class."""

    async def test_init(
        self, audio_analysis_service, mock_file_manager, mock_path_resolver, mock_config
    ):
        """Should initialize with correct dependencies and attributes."""
        assert audio_analysis_service.file_manager == mock_file_manager
        assert audio_analysis_service.path_resolver == mock_path_resolver
        assert audio_analysis_service.config == mock_config
        assert hasattr(audio_analysis_service, "analysis_client")
        assert hasattr(audio_analysis_service, "audio_buffer")
        assert hasattr(audio_analysis_service, "detection_buffer")
        assert hasattr(audio_analysis_service, "buffer_lock")
        assert audio_analysis_service._flush_task is not None

    @pytest.mark.asyncio
    async def test_process_audio_chunk_accumulates_buffer(
        self, audio_analysis_service, test_audio_data
    ):
        """Should accumulate audio data in buffer."""
        initial_buffer_length = len(audio_analysis_service.audio_buffer)
        audio_data = b"\x00\x01\x02\x03"
        await audio_analysis_service.process_audio_chunk(audio_data)
        assert len(audio_analysis_service.audio_buffer) > initial_buffer_length

    @pytest.mark.asyncio
    @patch(
        "birdnetpi.audio.audio_analysis_manager.AudioAnalysisManager._analyze_audio_chunk",
        new_callable=AsyncMock,
    )
    async def test_process_audio_chunk_calls_analyze__buffer_full(
        self, mock_analyze_audio_chunk, audio_analysis_service, test_audio_data
    ):
        """Should call _analyze_audio_chunk when buffer has enough data."""
        # Use test data for consistent configuration
        audio_analysis_service.config.sample_rate = test_audio_data["sample_rate"]
        audio_analysis_service.buffer_size_samples = test_audio_data["buffer_size_samples"]

        # Create enough audio data to trigger analysis
        chunk_size = test_audio_data["chunk_size"]
        audio_chunk = np.zeros(chunk_size, dtype=np.int16).tobytes()

        # Feed chunks until buffer is full
        chunks_needed = (test_audio_data["buffer_size_samples"] // chunk_size) + 1
        for _ in range(chunks_needed):
            await audio_analysis_service.process_audio_chunk(audio_chunk)

        # Should have called analyze at least once when buffer was full
        assert mock_analyze_audio_chunk.call_count >= 1

    @pytest.mark.asyncio
    @patch(
        "birdnetpi.audio.audio_analysis_manager.AudioAnalysisManager._send_detection_event",
        new_callable=AsyncMock,
    )
    async def test_analyze_audio_chunk__detections(
        self, mock_send_detection_event, audio_analysis_service, test_species_data, test_audio_data
    ):
        """Should send detection events for confident detections."""
        # Use test data for species detections
        audio_analysis_service.analysis_client.get_analysis_results.return_value = (
            test_species_data["mixed"]
        )

        # Use test audio chunk
        audio_chunk = test_audio_data["silence_chunk"]

        await audio_analysis_service._analyze_audio_chunk(audio_chunk)

        # Should have called send_detection_event twice
        # (for Robin and Crow, not Human below threshold)
        assert mock_send_detection_event.call_count == 2

        # Check the calls using test data
        calls = mock_send_detection_event.call_args_list
        expected_species = [call for call in test_species_data["mixed"] if call[1] >= 0.7]
        # First call arguments: (species_components, confidence, audio_bytes)
        # species_components should have scientific_name = "Turdus migratorius"
        assert calls[0][0][0].scientific_name == "Turdus migratorius"  # Robin scientific name
        assert calls[0][0][1] == expected_species[0][1]  # 0.85 (confidence)
        # Second call arguments - Crow
        assert calls[1][0][0].scientific_name == "Corvus brachyrhynchos"  # Crow scientific name
        assert calls[1][0][1] == expected_species[1][1]  # 0.72 (confidence)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event(
        self,
        mock_async_client,
        audio_analysis_service,
        mock_file_manager,
        mock_path_resolver,
        test_species_data,
        caplog,
    ):
        """Should successfully send a detection event and log info."""
        mock_post = AsyncMock(return_value=MagicMock(status_code=201))
        mock_async_client.return_value.__aenter__.return_value.post = mock_post

        # Use test data for species information - import SpeciesParser here
        from birdnetpi.species.parser import SpeciesParser

        species_tensor, confidence = test_species_data["confident"][
            0
        ]  # Turdus migratorius_American Robin, 0.85
        species_components = await SpeciesParser.parse_tensor_species(species_tensor)
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        await audio_analysis_service._send_detection_event(
            species_components, confidence, raw_audio_bytes
        )

        mock_path_resolver.get_detection_audio_path.assert_called_once()
        mock_file_manager.save_detection_audio.assert_called_once()
        mock_async_client.assert_called_once()
        mock_post.assert_called_once()
        assert "Detection event sent" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_audio_save_failure(
        self,
        mock_async_client,
        audio_analysis_service,
        mock_file_manager,
        test_species_data,
        caplog,
    ):
        """Should log an error and not send HTTP request if audio save fails."""
        mock_file_manager.save_detection_audio.side_effect = Exception("Audio save error")

        # Use test data for consistent species information
        species, confidence = test_species_data["confident"][1]  # Crow, 0.75
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        # Parse species tensor to get proper components
        from birdnetpi.species.parser import SpeciesParser

        species_components = await SpeciesParser.parse_tensor_species(species)
        await audio_analysis_service._send_detection_event(
            species_components, confidence, raw_audio_bytes
        )

        mock_async_client.assert_not_called()
        assert "Failed to save detection audio: Audio save error" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_httpx_request_error(
        self, mock_async_client, audio_analysis_service, test_species_data, caplog
    ):
        """Should buffer detection when httpx.RequestError occurs."""
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = (
            httpx.RequestError(
                "Network error",
                request=httpx.Request("POST", "http://test.com"),
            )
        )

        # Use test data for consistent species information
        species, confidence = test_species_data["confident"][2]  # Sparrow, 0.80
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        # Parse species tensor to get proper components
        from birdnetpi.species.parser import SpeciesParser

        species_components = await SpeciesParser.parse_tensor_species(species)
        await audio_analysis_service._send_detection_event(
            species_components, confidence, raw_audio_bytes
        )

        assert "FastAPI unavailable, buffering detection: Network error" in caplog.text
        # Extract scientific name from tensor format for log assertion
        scientific_name = species.split("_")[0]
        assert f"Buffered detection event for {scientific_name}" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_httpx_status_error(
        self, mock_async_client, audio_analysis_service, test_species_data, caplog
    ):
        """Should buffer detection when httpx.HTTPStatusError occurs."""
        mock_response = MagicMock(status_code=404, text="Not Found")
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = (
            httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        )

        # Use test data for consistent species information
        species, confidence = test_species_data["confident"][0]  # Robin, 0.85
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        # Parse species tensor to get proper components
        from birdnetpi.species.parser import SpeciesParser

        species_components = await SpeciesParser.parse_tensor_species(species)
        await audio_analysis_service._send_detection_event(
            species_components, confidence, raw_audio_bytes
        )

        assert "FastAPI unavailable, buffering detection: Not Found" in caplog.text
        # Extract scientific name from tensor format for log assertion
        scientific_name = species.split("_")[0]
        assert f"Buffered detection event for {scientific_name}" in caplog.text

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_detection_event_generic_exception(
        self, mock_async_client, audio_analysis_service, test_species_data, caplog
    ):
        """Should buffer detection when an unexpected exception occurs."""
        mock_async_client.return_value.__aenter__.return_value.post.side_effect = Exception(
            "Unexpected error"
        )

        # Use test data for consistent species information
        species, confidence = test_species_data["confident"][1]  # Crow, 0.75
        raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

        # Parse species tensor to get proper components
        from birdnetpi.species.parser import SpeciesParser

        species_components = await SpeciesParser.parse_tensor_species(species)
        await audio_analysis_service._send_detection_event(
            species_components, confidence, raw_audio_bytes
        )

        assert "Unexpected error sending detection, buffering: Unexpected error" in caplog.text
        # Extract scientific name from tensor format for log assertion
        scientific_name = species.split("_")[0]
        assert f"Buffered detection event for {scientific_name}" in caplog.text

    @pytest.mark.asyncio
    async def test_analyze_audio_chunk_handles_analysis_client_exception(
        self, audio_analysis_service, test_audio_data, caplog
    ):
        """Should handle and log exceptions from the analysis client."""
        # Mock the analysis client to raise an exception
        audio_analysis_service.analysis_client.get_analysis_results.side_effect = Exception(
            "Analysis failed"
        )

        # Use test audio chunk
        audio_chunk = test_audio_data["silence_chunk"]

        # This should not raise an exception, but should log an error
        await audio_analysis_service._analyze_audio_chunk(audio_chunk)

        # Should have logged the error
        assert "Error during BirdNET analysis: Analysis failed" in caplog.text

    @pytest.mark.asyncio
    async def test_analyze_audio_chunk__no_detections(
        self, audio_analysis_service, test_audio_data
    ):
        """Should handle case with no detections from analysis client."""
        # Mock analysis client to return empty results
        audio_analysis_service.analysis_client.get_analysis_results.return_value = []

        # Use test audio chunk
        audio_chunk = test_audio_data["silence_chunk"]

        # Should not raise exception with empty detections
        await audio_analysis_service._analyze_audio_chunk(audio_chunk)

        # Buffer should remain empty since no detections
        with audio_analysis_service.buffer_lock:
            assert len(audio_analysis_service.detection_buffer) == 0

    @pytest.mark.asyncio
    async def test_analyze_audio_chunk__invalid_audio_format(self, audio_analysis_service, caplog):
        """Should handle invalid audio format gracefully."""
        # Mock analysis client to raise specific audio format error
        audio_analysis_service.analysis_client.get_analysis_results.side_effect = ValueError(
            "Invalid audio format: expected float32"
        )

        # Create invalid audio chunk (wrong dtype)
        invalid_chunk = np.array([1000, 2000, 3000], dtype=np.int16)

        await audio_analysis_service._analyze_audio_chunk(invalid_chunk)

        assert "Error during BirdNET analysis: Invalid audio format" in caplog.text

    @pytest.mark.asyncio
    async def test_process_audio_chunk__empty_chunk(self, audio_analysis_service):
        """Should handle empty audio chunks gracefully."""
        initial_buffer_length = len(audio_analysis_service.audio_buffer)

        # Process empty chunk
        await audio_analysis_service.process_audio_chunk(b"")

        # Buffer length should remain unchanged
        assert len(audio_analysis_service.audio_buffer) == initial_buffer_length

    @pytest.mark.asyncio
    async def test_process_audio_chunk__malformed_audio(self, audio_analysis_service, caplog):
        """Should handle malformed audio data gracefully."""
        # Send malformed audio data that can't be processed
        malformed_data = b"\xff\xff\xff\xff"  # Invalid audio data

        # Should not raise exception
        await audio_analysis_service.process_audio_chunk(malformed_data)

        # Should still accumulate in buffer despite being malformed
        assert len(audio_analysis_service.audio_buffer) > 0


class TestDetectionBuffering:
    """Test the in-memory detection buffering functionality."""

    @pytest.fixture(autouse=True)
    def setup_cleanup(self, audio_analysis_service):
        """Set up and clean up for buffer flush task tests."""
        yield
        # Always stop the flush task after test to prevent background threads
        audio_analysis_service.stop_buffer_flush_task()

    async def test_start_buffer_flush_task(self, audio_analysis_service):
        """Should start background thread for buffer flushing."""
        assert audio_analysis_service._flush_task is not None
        assert audio_analysis_service._flush_task.is_alive()
        assert not audio_analysis_service._stop_flush_task

    async def test_stop_buffer_flush_task(self, audio_analysis_service):
        """Should stop the background buffer flush task cleanly."""
        # Verify task is running
        assert audio_analysis_service._flush_task.is_alive()

        # Stop the task
        audio_analysis_service.stop_buffer_flush_task()

        # Verify task is stopped
        assert audio_analysis_service._stop_flush_task
        # Task should stop within timeout
        time.sleep(0.2)  # Give it time to stop
        assert not audio_analysis_service._flush_task.is_alive()

    async def test_send_detection_event_buffers_on_http_failure(
        self, audio_analysis_service, mock_detection_data, caplog
    ):
        """Should buffer detection when FastAPI is unavailable."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock HTTP failure
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=httpx.Request("POST", "http://test.com")
            )

            # Clear buffer first
            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()

            confidence = 0.8
            raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

            # Create mock SpeciesComponents for test species
            from birdnetpi.species.parser import SpeciesComponents

            species_components = SpeciesComponents(
                "Test species", "Test Species", "Test Species (Test species)"
            )
            await audio_analysis_service._send_detection_event(
                species_components, confidence, raw_audio_bytes
            )

            # Verify detection was buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1
                buffered = next(iter(audio_analysis_service.detection_buffer))
                assert buffered["species_tensor"] == "Test species_Test Species"
                assert buffered["confidence"] == confidence

            assert "FastAPI unavailable, buffering detection" in caplog.text
            assert "Buffered detection event for Test species (buffer size: 1)" in caplog.text

    async def test_send_detection_event_buffers_on_http_status_error(
        self, audio_analysis_service, caplog
    ):
        """Should buffer detection when FastAPI returns HTTP error."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock HTTP status error
            mock_response = MagicMock(status_code=500)
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)
            )

            # Clear buffer first
            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()

            confidence = 0.8
            raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

            # Create mock SpeciesComponents for test species
            from birdnetpi.species.parser import SpeciesComponents

            species_components = SpeciesComponents(
                "Test species", "Test Species", "Test Species (Test species)"
            )
            await audio_analysis_service._send_detection_event(
                species_components, confidence, raw_audio_bytes
            )

            # Verify detection was buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1

            assert "FastAPI unavailable, buffering detection" in caplog.text

    async def test_send_detection_event_buffers_on_generic_exception(
        self, audio_analysis_service, caplog
    ):
        """Should buffer detection when unexpected exception occurs during HTTP request."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock generic exception
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception(
                "Unexpected error"
            )

            # Clear buffer first
            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()

            confidence = 0.8
            raw_audio_bytes = np.array([1, 2, 3], dtype=np.int16).tobytes()

            # Create mock SpeciesComponents for test species
            from birdnetpi.species.parser import SpeciesComponents

            species_components = SpeciesComponents(
                "Test species", "Test Species", "Test Species (Test species)"
            )
            await audio_analysis_service._send_detection_event(
                species_components, confidence, raw_audio_bytes
            )

            # Verify detection was buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1

            assert "Unexpected error sending detection, buffering" in caplog.text

    async def test_flush_detection_buffer__empty_buffer(self, audio_analysis_service, caplog):
        """Should handle empty buffer gracefully."""
        # Clear buffer
        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.clear()

        await audio_analysis_service._flush_detection_buffer()

        # Should not log anything for empty buffer
        assert "Attempting to flush" not in caplog.text

    async def test_flush_detection_buffer_successful_flush(self, audio_analysis_service, caplog):
        """Should successfully flush buffered detections."""
        # Add test detection to buffer (in new format)
        test_detection = {
            "species_tensor": "Turdus migratorius_American Robin",
            "scientific_name": "Turdus migratorius",
            "common_name": "American Robin",
            "confidence": 0.9,
            "timestamp": datetime.now().isoformat(),
        }

        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.append(test_detection)

        with patch("httpx.AsyncClient") as mock_client:
            # Mock successful HTTP response
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            await audio_analysis_service._flush_detection_buffer()

            # Verify buffer is empty after successful flush
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 0

            # Verify HTTP request was made
            mock_client.return_value.__aenter__.return_value.post.assert_called_once()

            assert "Attempting to flush 1 buffered detections" in caplog.text
            assert "Successfully flushed 1 buffered detections" in caplog.text

    async def test_flush_detection_buffer_partial_failure(self, audio_analysis_service, caplog):
        """Should re-buffer failed detections and flush successful ones."""
        # Add multiple test detections to buffer (in new format)
        test_detections = [
            {
                "species_tensor": "Turdus migratorius_American Robin",
                "scientific_name": "Turdus migratorius",
                "common_name": "American Robin",
                "confidence": 0.9,
                "timestamp": datetime.now().isoformat(),
            },
            {
                "species_tensor": "Corvus brachyrhynchos_American Crow",
                "scientific_name": "Corvus brachyrhynchos",
                "common_name": "American Crow",
                "confidence": 0.8,
                "timestamp": datetime.now().isoformat(),
            },
            {
                "species_tensor": "Passer domesticus_House Sparrow",
                "scientific_name": "Passer domesticus",
                "common_name": "House Sparrow",
                "confidence": 0.7,
                "timestamp": datetime.now().isoformat(),
            },
        ]

        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.clear()
            for detection in test_detections:
                audio_analysis_service.detection_buffer.append(detection)

        with patch("httpx.AsyncClient") as mock_client:
            # Mock mixed success/failure responses
            post_mock = mock_client.return_value.__aenter__.return_value.post

            responses = []
            # First call succeeds
            success_response = MagicMock()
            success_response.raise_for_status = MagicMock()
            responses.append(success_response)

            # Second call fails
            responses.append(httpx.RequestError("Connection failed", request=MagicMock()))

            # Third call succeeds
            success_response2 = MagicMock()
            success_response2.raise_for_status = MagicMock()
            responses.append(success_response2)

            post_mock.side_effect = responses

            await audio_analysis_service._flush_detection_buffer()

            # Verify one detection was re-buffered (the failed one)
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1
                rebuffered = next(iter(audio_analysis_service.detection_buffer))
                assert (
                    rebuffered["scientific_name"] == "Corvus brachyrhynchos"
                )  # The middle one that failed

            assert "Attempting to flush 3 buffered detections" in caplog.text
            assert "Successfully flushed 2 buffered detections" in caplog.text
            assert "Re-buffered 1 failed detections" in caplog.text

    async def test_flush_detection_buffer_all_failures(self, audio_analysis_service, caplog):
        """Should re-buffer all detections when all flush attempts fail."""
        # Add test detection to buffer (in new format)
        test_detection = {
            "species_tensor": "Turdus migratorius_American Robin",
            "scientific_name": "Turdus migratorius",
            "common_name": "American Robin",
            "confidence": 0.9,
            "timestamp": datetime.now().isoformat(),
        }

        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.clear()
            audio_analysis_service.detection_buffer.append(test_detection)

        with patch("httpx.AsyncClient") as mock_client:
            # Mock HTTP failure
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            await audio_analysis_service._flush_detection_buffer()

            # Verify detection was re-buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1
                rebuffered = next(iter(audio_analysis_service.detection_buffer))
                assert rebuffered["scientific_name"] == "Turdus migratorius"

            assert "Attempting to flush 1 buffered detections" in caplog.text
            assert "Re-buffered 1 failed detections" in caplog.text
            assert "Successfully flushed" not in caplog.text  # No successful flushes

    async def test_flush_detection_buffer_unexpected__error_handling(
        self, audio_analysis_service, caplog
    ):
        """Should handle unexpected errors during flush and re-buffer detections."""
        # Add test detection to buffer (in new format)
        test_detection = {
            "species_tensor": "Turdus migratorius_American Robin",
            "scientific_name": "Turdus migratorius",
            "common_name": "American Robin",
            "confidence": 0.9,
            "timestamp": datetime.now().isoformat(),
        }

        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.clear()
            audio_analysis_service.detection_buffer.append(test_detection)

        with patch("httpx.AsyncClient") as mock_client:
            # Mock unexpected exception
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception(
                "Unexpected error"
            )

            await audio_analysis_service._flush_detection_buffer()

            # Verify detection was re-buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1

            assert "Attempting to flush 1 buffered detections" in caplog.text
            assert "Unexpected error flushing detection" in caplog.text
            assert "Re-buffered 1 failed detections" in caplog.text

    @patch("birdnetpi.audio.audio_analysis_manager.BirdDetectionService")
    async def test_detection_buffer_max_size_enforcement(
        self, mock_analysis_client_class, audio_analysis_service
    ):
        """Should enforce maximum buffer size by evicting oldest detections."""
        # Mock the BirdDetectionService constructor
        mock_analysis_client = MagicMock()
        mock_analysis_client_class.return_value = mock_analysis_client

        # Mock MultilingualDatabaseService and AsyncSession
        mock_multilingual_service = MagicMock()
        # Make get_best_common_name async and return a dict with common_name
        mock_multilingual_service.get_best_common_name = AsyncMock(
            return_value={"common_name": "Test Bird"}
        )
        mock_session = MagicMock()

        # Initialize SpeciesParser with the mock service
        from birdnetpi.species.parser import SpeciesParser

        SpeciesParser._instance = None  # Reset singleton
        SpeciesParser(mock_multilingual_service)  # Initialize with mock

        # Set a small max size for testing
        max_size = 5
        service = AudioAnalysisManager(
            audio_analysis_service.file_manager,
            audio_analysis_service.path_resolver,
            audio_analysis_service.config,
            mock_multilingual_service,
            mock_session,
            detection_buffer_max_size=max_size,
            buffer_flush_interval=1.0,
        )
        service.analysis_client = mock_analysis_client

        # Add more detections than max size
        with service.buffer_lock:
            for i in range(max_size + 3):
                detection = {
                    "species_tensor": f"Species_{i}",
                    "confidence": 0.8,
                    "timestamp": datetime.now().isoformat(),
                }
                service.detection_buffer.append(detection)

        # Verify buffer respects max size
        with service.buffer_lock:
            assert len(service.detection_buffer) == max_size
            # Should contain the latest detections
            latest_species = [d["species_tensor"] for d in service.detection_buffer]
            assert "Species_3" in latest_species  # Should keep recent ones
            assert "Species_0" not in latest_species  # Should have evicted oldest

        service.stop_buffer_flush_task()

    async def test_buffer_thread_safety(self, audio_analysis_service):
        """Should handle concurrent buffer operations safely."""
        results = []

        def add_detections(thread_id: int):
            """Add detections from a thread."""
            try:
                for i in range(10):
                    detection = {
                        "species_tensor": f"Thread{thread_id}_Species_{i}",
                        "confidence": 0.8,
                        "timestamp": datetime.now().isoformat(),
                    }
                    with audio_analysis_service.buffer_lock:
                        audio_analysis_service.detection_buffer.append(detection)
                    time.sleep(0.001)  # Small delay to increase chance of race conditions
                results.append(f"thread_{thread_id}_success")
            except Exception as e:
                results.append(f"thread_{thread_id}_error_{e}")

        # Clear buffer first
        with audio_analysis_service.buffer_lock:
            audio_analysis_service.detection_buffer.clear()

        # Start multiple threads adding to buffer
        threads = []
        for i in range(3):
            thread = threading.Thread(target=add_detections, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=1.0)

        # Verify all threads completed successfully
        assert len(results) == 3
        assert all("success" in result for result in results)

        # Verify buffer contains detections from all threads
        with audio_analysis_service.buffer_lock:
            buffer_size = len(audio_analysis_service.detection_buffer)
            species_list = [d["species_tensor"] for d in audio_analysis_service.detection_buffer]

        # Should have some detections (might be less than 30 due to buffer size limit)
        assert buffer_size > 0
        # Should have detections from multiple threads
        thread_prefixes = {species.split("_")[0] for species in species_list}
        assert len(thread_prefixes) > 1

    async def test_background_flush_integration(self, audio_analysis_service, caplog):
        """Should automatically flush buffer in background with working FastAPI."""
        # Use faster flush interval for testing
        audio_analysis_service.flush_interval = 0.1

        with patch("httpx.AsyncClient") as mock_client:
            # Mock successful HTTP response
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Add detection to buffer
            test_detection = {
                "species_tensor": "Turdus migratorius",
                "confidence": 0.9,
                "timestamp": datetime.now().isoformat(),
            }

            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()
                audio_analysis_service.detection_buffer.append(test_detection)

            # Wait for background flush to occur
            await asyncio.sleep(0.2)

            # Buffer should be empty after automatic flush
            with audio_analysis_service.buffer_lock:
                buffer_size = len(audio_analysis_service.detection_buffer)

            assert buffer_size == 0
            assert "Successfully flushed 1 buffered detections" in caplog.text

    async def test_background_flush__failed_requests(self, audio_analysis_service, caplog):
        """Should keep retrying buffered detections in background when FastAPI fails."""
        # Use faster flush interval for testing
        audio_analysis_service.flush_interval = 0.1

        with patch("httpx.AsyncClient") as mock_client:
            # Mock HTTP failure initially
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            # Add detection to buffer
            test_detection = {
                "species_tensor": "Turdus migratorius",
                "confidence": 0.9,
                "timestamp": datetime.now().isoformat(),
            }

            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()
                audio_analysis_service.detection_buffer.append(test_detection)

            # Wait for first flush attempt (should fail)
            await asyncio.sleep(0.2)

            # Buffer should still contain the detection
            with audio_analysis_service.buffer_lock:
                buffer_size = len(audio_analysis_service.detection_buffer)

            assert buffer_size == 1
            assert "Re-buffered 1 failed detections" in caplog.text

            # Now mock successful response
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.side_effect = None
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Wait for another flush attempt (should succeed)
            await asyncio.sleep(0.2)

            # Buffer should now be empty
            with audio_analysis_service.buffer_lock:
                buffer_size = len(audio_analysis_service.detection_buffer)

            assert buffer_size == 0
            assert "Successfully flushed 1 buffered detections" in caplog.text


class TestDetectionBufferingIntegration:
    """Integration tests for detection buffering with full workflow."""

    @pytest.fixture(autouse=True)
    def setup_cleanup(self, audio_analysis_service):
        """Set up and clean up for integration tests."""
        yield
        audio_analysis_service.stop_buffer_flush_task()

    async def test_end_to_end_detection__buffering(self, audio_analysis_service, caplog):
        """Should buffer detections during HTTP failures and flush when service recovers."""
        # Mock analysis to return confident detection
        audio_analysis_service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85),
        ]

        # Mock file manager
        audio_analysis_service.file_manager.save_detection_audio.return_value = MagicMock(
            file_path="/mock/audio.wav",
            duration=3.0,
            size_bytes=1000,
        )

        with patch("httpx.AsyncClient") as mock_client:
            # First, simulate FastAPI unavailable
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            # Clear buffer
            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()

            # Process audio that triggers detection
            audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1  # 3 seconds of low-level audio
            await audio_analysis_service._analyze_audio_chunk(audio_chunk)

            # Verify detection was buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1
                buffered = next(iter(audio_analysis_service.detection_buffer))
                assert buffered["scientific_name"] == "Turdus migratorius"
                assert buffered["confidence"] == 0.85

            assert "Buffered detection event for Turdus migratorius" in caplog.text

            # Now simulate FastAPI becomes available
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.side_effect = None
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Manually trigger flush (simulating background flush)
            await audio_analysis_service._flush_detection_buffer()

            # Verify buffer is empty after flush
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 0

            assert "Successfully flushed 1 buffered detections" in caplog.text

    async def test_mixed_success__failure_detection_processing(
        self, audio_analysis_service, caplog
    ):
        """Should handle mixed scenarios where some detections succeed and others buffer."""
        # Mock analysis to return multiple detections
        audio_analysis_service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85),
            ("Corvus brachyrhynchos_American Crow", 0.75),
            ("Passer domesticus_House Sparrow", 0.80),
        ]

        # Mock file manager
        audio_analysis_service.file_manager.save_detection_audio.return_value = MagicMock(
            file_path="/mock/audio.wav",
            duration=3.0,
            size_bytes=1000,
        )

        with patch("httpx.AsyncClient") as mock_client:
            post_mock = mock_client.return_value.__aenter__.return_value.post

            # Mock responses: success, failure, success
            responses = []

            # First detection succeeds
            success_response = MagicMock()
            success_response.raise_for_status = MagicMock()
            responses.append(success_response)

            # Second detection fails
            responses.append(httpx.RequestError("Connection failed", request=MagicMock()))

            # Third detection succeeds
            success_response2 = MagicMock()
            success_response2.raise_for_status = MagicMock()
            responses.append(success_response2)

            post_mock.side_effect = responses

            # Clear buffer
            with audio_analysis_service.buffer_lock:
                audio_analysis_service.detection_buffer.clear()

            # Process audio that triggers detections
            audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
            await audio_analysis_service._analyze_audio_chunk(audio_chunk)

            # Verify only failed detection was buffered
            with audio_analysis_service.buffer_lock:
                assert len(audio_analysis_service.detection_buffer) == 1
                buffered = next(iter(audio_analysis_service.detection_buffer))
                assert buffered["scientific_name"] == "Corvus brachyrhynchos"

            # Verify successful sends were logged
            assert "Detection event sent: Turdus migratorius" in caplog.text
            assert "Detection event sent: Passer domesticus" in caplog.text
            # Verify failed detection was buffered
            assert "Buffered detection event for Corvus brachyrhynchos" in caplog.text
