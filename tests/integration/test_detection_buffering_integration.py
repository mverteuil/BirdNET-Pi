"""Integration tests for detection buffering system.

These tests verify end-to-end scenarios combining AudioAnalysisManager
buffering with admin operations like generate_dummy_data.
"""

import asyncio
import logging
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest

import birdnetpi.cli.generate_dummy_data as gdd
from birdnetpi.audio.audio_analysis_manager import AudioAnalysisManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.system.file_manager import FileManager


@pytest.fixture
def mock_config():
    """Return a mock BirdNETConfig instance for integration tests."""
    mock = MagicMock(spec=BirdNETConfig)
    mock.sample_rate = 48000
    mock.audio_channels = 1
    mock.latitude = 40.7128
    mock.longitude = -74.0060
    mock.sensitivity_setting = 1.25
    mock.species_confidence_threshold = 0.7
    mock.analysis_overlap = 0.5
    mock.detections_endpoint = "http://localhost:8000/api/v1/detections/"
    return mock


@pytest.fixture
def mock_file_manager():
    """Return a mock FileManager instance for integration tests."""
    from pathlib import Path

    # FileManager returns the same relative path it receives
    relative_path = Path("recordings/Test_bird/20240101_120000.wav")
    mock = MagicMock(spec=FileManager)
    mock.save_detection_audio.return_value = MagicMock(
        file_path=relative_path,
        duration=3.0,
        size_bytes=1000,
    )
    return mock


@pytest.fixture
def mock_path_resolver(tmp_path, path_resolver):
    """Return a PathResolver instance for integration tests."""
    # Use the global path_resolver fixture and customize it
    # get_detection_audio_path expects scientific_name and common_name parameters
    path_resolver.get_detection_audio_path = lambda scientific_name, common_name: (
        tmp_path / "recordings/Test_bird/20240101_120000.wav"
    )
    return path_resolver


@pytest.fixture
def audio_analysis_service_integration(
    mock_file_manager,
    mock_path_resolver,
    mock_config,
):
    """Yield an AudioAnalysisManager instance for integration testing with proper cleanup."""
    with patch(
        "birdnetpi.audio.audio_analysis_manager.BirdDetectionService"
    ) as mock_analysis_client_class:
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

        service = AudioAnalysisManager(
            mock_file_manager,
            mock_path_resolver,
            mock_config,
            mock_multilingual_service,
            mock_session,
            detection_buffer_max_size=50,  # Reasonable size for integration tests
            buffer_flush_interval=0.1,  # Fast interval for testing
        )
        service.analysis_client = mock_analysis_client
        # Start the buffer flush task for automatic flushing
        service.start_buffer_flush_task()

        # Ensure the task is stopped after the test
        yield service
        service.stop_buffer_flush_task()


@pytest.fixture(autouse=True)
def caplog_integration(caplog):
    """Fixture to capture logs for integration tests."""
    caplog.set_level(logging.INFO, logger="birdnetpi.audio.audio_analysis_manager")
    caplog.set_level(logging.INFO, logger="birdnetpi.cli.generate_dummy_data")
    yield


class TestDetectionBufferingEndToEnd:
    """End-to-end integration tests for detection buffering system."""

    async def test_detection_buffering_during_fastapi_outage(
        self, audio_analysis_service_integration, caplog
    ):
        """Should buffer detections during FastAPI outage and flush when available."""
        service = audio_analysis_service_integration

        # Mock analysis to return detections
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85),
            ("Corvus brachyrhynchos_American Crow", 0.75),
        ]

        # Phase 1: FastAPI unavailable - detections should be buffered
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            # Clear buffer
            with service.buffer_lock:
                service.detection_buffer.clear()

            # Process audio that triggers detections
            audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
            await service._analyze_audio_chunk(audio_chunk)

            # Verify detections were buffered
            with service.buffer_lock:
                assert len(service.detection_buffer) == 2
                # Check scientific names instead since common names might be MagicMock
                scientific_names = [d["scientific_name"] for d in service.detection_buffer]
                assert "Turdus migratorius" in scientific_names
                assert "Corvus brachyrhynchos" in scientific_names

            assert "Buffered detection event for Turdus migratorius" in caplog.text
            assert "Buffered detection event for Corvus brachyrhynchos" in caplog.text

        # Phase 2: FastAPI becomes available - buffered detections should flush
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Wait for background flush to occur
            await asyncio.sleep(0.2)

            # Buffer should be empty after automatic flush
            with service.buffer_lock:
                buffer_size = len(service.detection_buffer)

            assert buffer_size == 0
            assert "Successfully flushed buffered detections" in caplog.text

    async def test_concurrent_detection__admin_operations(
        self, audio_analysis_service_integration, caplog
    ):
        """Should handle concurrent detections during admin operations without data loss."""
        service = audio_analysis_service_integration

        # Mock analysis to return detections
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85),
        ]

        detection_results = {"detections_processed": 0, "detections_buffered": 0}
        admin_operation_complete = {"value": False}

        async def simulate_continuous_detections():
            """Simulate continuous bird detections."""
            try:
                # Process multiple audio chunks while admin operation runs
                for _i in range(5):
                    audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                    await service._analyze_audio_chunk(audio_chunk)
                    detection_results["detections_processed"] += 1
                    await asyncio.sleep(0.05)  # Small delay between detections
            except Exception as e:
                pytest.fail(f"Detection processing failed: {e}")

        def simulate_admin_operation():
            """Simulate admin operation that affects FastAPI."""
            time.sleep(0.1)  # Let some detections start
            time.sleep(0.5)  # Admin operation in progress
            admin_operation_complete["value"] = True

        # Clear buffer
        with service.buffer_lock:
            service.detection_buffer.clear()

        # Patch HTTP client for the entire test duration to simulate FastAPI being down
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            # Start concurrent operations
            admin_thread = threading.Thread(target=simulate_admin_operation)
            admin_thread.start()

            # Run detections concurrently
            await simulate_continuous_detections()

            # Wait for admin operation to complete
            admin_thread.join(timeout=1.0)
            assert admin_operation_complete["value"], "Admin operation should complete"

            # Verify some detections were processed
            assert detection_results["detections_processed"] == 5

            # Verify some detections were buffered during outage
            with service.buffer_lock:
                buffer_size = len(service.detection_buffer)

            assert buffer_size > 0, "Some detections should be buffered during admin operation"
        assert "Buffered detection event for Turdus migratorius" in caplog.text

    @patch("birdnetpi.audio.audio_analysis_manager.BirdDetectionService")
    async def test_buffer_overflow_handling_during_extended_outage(
        self,
        mock_analysis_client_class,
        audio_analysis_service_integration,
        caplog,
    ):
        """Should handle buffer overflow gracefully during extended FastAPI outages."""
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

        # Create service with small buffer for testing overflow
        service = AudioAnalysisManager(
            audio_analysis_service_integration.file_manager,
            audio_analysis_service_integration.path_resolver,
            audio_analysis_service_integration.config,
            mock_multilingual_service,
            mock_session,
            detection_buffer_max_size=3,  # Small buffer to trigger overflow
            buffer_flush_interval=0.1,
        )

        # Mock analysis
        service.analysis_client = MagicMock()
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85)
        ]

        try:
            with patch("httpx.AsyncClient") as mock_client:
                # Mock persistent HTTP failure
                mock_client.return_value.__aenter__.return_value.post.side_effect = (
                    httpx.RequestError("Connection failed", request=MagicMock())
                )

                # Clear buffer
                with service.buffer_lock:
                    service.detection_buffer.clear()

                # Process many detections to trigger overflow
                for _i in range(10):
                    audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                    await service._analyze_audio_chunk(audio_chunk)

                # Verify buffer respects max size (oldest detections evicted)
                with service.buffer_lock:
                    assert len(service.detection_buffer) == 3  # Max buffer size

                # Verify logging indicates buffering is happening
                assert "Buffered detection event for Turdus migratorius" in caplog.text

        finally:
            service.stop_buffer_flush_task()

    async def test_detection_recovery_after_service_restart(
        self, audio_analysis_service_integration, caplog
    ):
        """Should flush buffered detections when service recovers after restart simulation."""
        service = audio_analysis_service_integration

        # Mock analysis
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85)
        ]

        # Phase 1: Service unavailable, buffer detections
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.RequestError(
                "Connection failed", request=MagicMock()
            )

            # Clear buffer and add detections
            with service.buffer_lock:
                service.detection_buffer.clear()

            # Process detections during outage
            for _ in range(3):
                audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                await service._analyze_audio_chunk(audio_chunk)

            # Verify detections are buffered
            with service.buffer_lock:
                assert len(service.detection_buffer) == 3

        # Phase 2: Simulate service recovery
        with patch("httpx.AsyncClient") as mock_client:
            # Mock successful responses
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Wait for background flush to process buffered detections
            await asyncio.sleep(0.3)

            # Buffer should be empty after successful flush
            with service.buffer_lock:
                buffer_size = len(service.detection_buffer)

            assert buffer_size == 0
            assert "Successfully flushed buffered detections" in caplog.text

    async def test_mixed_success__failure_during_partial_recovery(
        self, audio_analysis_service_integration, caplog
    ):
        """Should handle mixed success/failure scenarios during partial service recovery."""
        service = audio_analysis_service_integration

        # Mock analysis to return multiple detections
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85),
            ("Corvus brachyrhynchos_American Crow", 0.75),
            ("Passer domesticus_House Sparrow", 0.80),
            ("Cardinalis cardinalis_Northern Cardinal", 0.90),
        ]

        with patch("httpx.AsyncClient") as mock_client:
            post_mock = mock_client.return_value.__aenter__.return_value.post

            # Mock intermittent failures: success, fail, success, fail
            responses = []
            for i in range(4):
                if i % 2 == 0:  # Even indices succeed
                    success_response = MagicMock()
                    success_response.raise_for_status = MagicMock()
                    responses.append(success_response)
                else:  # Odd indices fail
                    responses.append(
                        httpx.RequestError("Intermittent failure", request=MagicMock())
                    )

            post_mock.side_effect = responses

            # Clear buffer
            with service.buffer_lock:
                service.detection_buffer.clear()

            # Process audio that triggers all detections
            audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
            await service._analyze_audio_chunk(audio_chunk)

            # Verify only failed detections were buffered
            with service.buffer_lock:
                buffer_size = len(service.detection_buffer)
                if buffer_size > 0:
                    buffered_scientific_names = [
                        d["scientific_name"] for d in service.detection_buffer
                    ]
                else:
                    buffered_scientific_names = []

            # Should have 2 failed detections buffered (Crow and Cardinal)
            assert buffer_size == 2
            assert "Corvus brachyrhynchos" in buffered_scientific_names
            assert "Cardinalis cardinalis" in buffered_scientific_names

            # Verify successful sends were logged
            assert "Detection event sent" in caplog.text
            assert "Bird detected: Turdus migratorius" in caplog.text
            assert "Bird detected: Passer domesticus" in caplog.text

            # Verify failed detections were buffered
            assert "Buffered detection event for Corvus brachyrhynchos" in caplog.text
            assert "Buffered detection event for Cardinalis cardinalis" in caplog.text


class TestDetectionBufferingWithAdminOperations:
    """Integration tests combining detection buffering with actual admin operations."""

    async def test_generate_dummy_data__active_detection_service(
        self, audio_analysis_service_integration, caplog
    ):
        """Should coordinate detection buffering during generate_dummy_data execution."""
        service = audio_analysis_service_integration

        # Mock analysis
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85)
        ]

        try:
            # Start with working FastAPI
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                # Clear buffer
                with service.buffer_lock:
                    service.detection_buffer.clear()

                # Process some initial detections (should succeed)
                audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                await service._analyze_audio_chunk(audio_chunk)

                # Buffer should be empty (successful sends)
                with service.buffer_lock:
                    initial_buffer_size = len(service.detection_buffer)
                assert initial_buffer_size == 0
                assert "Detection event sent" in caplog.text
                assert "Bird detected: Turdus migratorius" in caplog.text

            # Simulate admin operation affecting FastAPI
            with (
                patch("birdnetpi.cli.generate_dummy_data.PathResolver") as mock_path_resolver,
                patch(
                    "birdnetpi.cli.generate_dummy_data.DatabaseService"
                ) as _mock_database_service,
                patch("birdnetpi.cli.generate_dummy_data.DataManager") as mock_data_manager,
                patch(
                    "birdnetpi.cli.generate_dummy_data.SystemControlService"
                ) as mock_system_control_service,
                patch(
                    "birdnetpi.cli.generate_dummy_data.generate_dummy_detections"
                ) as _mock_generate_dummy_detections,
                patch("birdnetpi.cli.generate_dummy_data.time") as _mock_time,
                patch("birdnetpi.cli.generate_dummy_data.os") as mock_os,
                patch("birdnetpi.cli.generate_dummy_data.ConfigManager") as mock_config_parser,
            ):
                # Configure mocks for generate_dummy_data
                from pathlib import Path

                mock_db_path = MagicMock(spec=Path)
                mock_db_path.exists.return_value = False
                mock_db_path.stat.return_value.st_size = 0
                mock_path_resolver.return_value.get_database_path.return_value = mock_db_path

                # Create a proper temp config path to avoid MagicMock file creation
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as config_file:
                    config_file.write("site_name: Test\nlatitude: 0.0\nlongitude: 0.0\n")
                    config_path = Path(config_file.name)

                mock_path_resolver.return_value.get_birdnetpi_config_path.return_value = config_path
                mock_config_parser.return_value.load.return_value = MagicMock()

                mock_os.path.exists.return_value = False
                mock_os.getenv.return_value = "false"  # SBC environment
                mock_system_control_service.return_value.get_service_status.return_value = "active"
                mock_data_manager.return_value.get_all_detections.return_value = []

                # During admin operation, simulate FastAPI being down
                with patch("httpx.AsyncClient") as mock_client:
                    mock_client.return_value.__aenter__.return_value.post.side_effect = (
                        httpx.RequestError("Service temporarily unavailable", request=MagicMock())
                    )

                    # Process detections during admin operation
                    await service._analyze_audio_chunk(audio_chunk)

                    # Verify detection was buffered during admin operation
                    with service.buffer_lock:
                        admin_buffer_size = len(service.detection_buffer)
                    assert admin_buffer_size == 1
                    assert "Buffered detection event for Turdus migratorius" in caplog.text

                    # Run the admin operation
                    await gdd.run()

            # After admin operation, FastAPI should be available again
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                # Wait for background flush to process buffered detection
                await asyncio.sleep(0.2)

                # Buffer should be empty after admin operation completes
                with service.buffer_lock:
                    final_buffer_size = len(service.detection_buffer)
                assert final_buffer_size == 0
                assert "Successfully flushed buffered detections" in caplog.text

        finally:
            service.stop_buffer_flush_task()

    async def test_buffer_persistence_across_multiple_admin_cycles(
        self, audio_analysis_service_integration, caplog
    ):
        """Should maintain buffer integrity across multiple admin operation cycles."""
        service = audio_analysis_service_integration

        # Mock analysis
        service.analysis_client.get_analysis_results.return_value = [
            ("Turdus migratorius_American Robin", 0.85)
        ]

        try:
            # Clear buffer
            with service.buffer_lock:
                service.detection_buffer.clear()

            # Cycle 1: Build up buffer during first admin operation
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post.side_effect = (
                    httpx.RequestError("Service down", request=MagicMock())
                )

                # Add detections to buffer
                for _ in range(3):
                    audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                    await service._analyze_audio_chunk(audio_chunk)

                with service.buffer_lock:
                    cycle1_buffer_size = len(service.detection_buffer)
                assert cycle1_buffer_size == 3

            # Cycle 2: Partial flush, then more failures
            with patch("httpx.AsyncClient") as mock_client:
                post_mock = mock_client.return_value.__aenter__.return_value.post

                # First flush attempt: partial success
                responses = [
                    MagicMock(),  # Success
                    httpx.RequestError("Still failing", request=MagicMock()),  # Failure
                    MagicMock(),  # Success
                ]
                for response in responses:
                    if hasattr(response, "raise_for_status"):
                        response.raise_for_status = MagicMock()

                post_mock.side_effect = responses

                # Manually trigger flush
                await service._flush_detection_buffer()

                # Should have 1 detection re-buffered (the failed one)
                with service.buffer_lock:
                    cycle2_buffer_size = len(service.detection_buffer)
                assert cycle2_buffer_size == 1

                # Add more detections during continued issues
                mock_client.return_value.__aenter__.return_value.post.side_effect = (
                    httpx.RequestError("Still down", request=MagicMock())
                )

                for _ in range(2):
                    audio_chunk = np.ones(48000 * 3, dtype=np.float32) * 0.1
                    await service._analyze_audio_chunk(audio_chunk)

                with service.buffer_lock:
                    cycle2_final_buffer_size = len(service.detection_buffer)
                assert cycle2_final_buffer_size == 3  # 1 from partial flush + 2 new

            # Cycle 3: Full recovery and complete flush
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

                # Wait for background flush
                await asyncio.sleep(0.2)

                # All detections should be flushed
                with service.buffer_lock:
                    final_buffer_size = len(service.detection_buffer)
                assert final_buffer_size == 0

                assert "Successfully flushed" in caplog.text

        finally:
            service.stop_buffer_flush_task()
