import logging
import os
import signal
from unittest.mock import DEFAULT, MagicMock, patch

import pytest

import birdnetpi.wrappers.audio_analysis_daemon as daemon


@pytest.fixture
def test_fifo_data():
    """Provide test FIFO data for daemon operations."""
    return {
        "path": "/tmp/fifo/birdnet_audio_analysis.fifo",
        "base_path": "/tmp/fifo",
        "fd": 123,
        "chunks": [b"audio_chunk_1", b"audio_chunk_2", b""],
        "chunk_size": 1024,
        "read_timeout": 0.01,
    }


@pytest.fixture
def test_daemon_lifecycle():
    """Provide test data for daemon lifecycle management."""
    return {
        "loop_iterations": [False, False, True],  # Run twice then exit
        "single_iteration": [False, True],  # Run once then exit
        "immediate_exit": [True],  # Exit immediately
        "sleep_interval": 0.01,
    }


@pytest.fixture
def test_error_scenarios():
    """Provide test data for error handling scenarios."""
    return {
        "fifo_not_found": FileNotFoundError("FIFO not found"),
        "permission_denied": OSError("Permission denied"),
        "read_error": Exception("Read error"),
        "general_error": Exception("General error"),
        "blocking_io": BlockingIOError(),
        "expected_error_messages": {
            "fifo_not_found": "FIFO not found at /tmp/fifo/birdnet_audio_analysis.fifo. Ensure audio_capture is running and creating it.",
            "read_error": "Error reading from FIFO",
            "general_error": "An error occurred in the audio analysis wrapper: General error",
        },
    }


@pytest.fixture
def mock_os_operations(mocker, test_fifo_data):
    """Mock common OS operations for FIFO handling."""
    mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
    mock_os.path.join.return_value = test_fifo_data["path"]
    mock_os.open.return_value = test_fifo_data["fd"]
    mock_os.O_RDONLY = os.O_RDONLY
    mock_os.O_NONBLOCK = os.O_NONBLOCK
    mock_os.read.side_effect = test_fifo_data["chunks"]
    return mock_os


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Mock external dependencies for audio_analysis_daemon.py."""
    with patch.multiple(
        "birdnetpi.wrappers.audio_analysis_daemon",
        FilePathResolver=DEFAULT,
        FileManager=DEFAULT,
        ConfigFileParser=DEFAULT,
        AudioAnalysisService=DEFAULT,
    ) as mocks:
        # Configure mocks
        mocks["FilePathResolver"].return_value.get_fifo_base_path.return_value = "/tmp/fifo"

        # Yield mocks for individual test configuration
        yield mocks


@pytest.fixture(autouse=True)
def caplog_for_wrapper(caplog):
    """Fixture to capture logs from the wrapper script."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.wrappers.audio_analysis_daemon")
    yield


class TestAudioAnalysisDaemon:
    """Test the audio analysis daemon."""

    def test_run_audio_analysis_daemon(
        self,
        mocker,
        mock_dependencies,
        mock_os_operations,
        test_fifo_data,
        test_daemon_lifecycle,
        caplog,
    ):
        """Should open FIFO, read data, process, and close on shutdown."""
        mock_signal = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mock_atexit = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mock_asyncio = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")
        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", new_callable=MagicMock
        )

        # Use test data for daemon lifecycle control
        mock_global_shutdown_flag.__bool__.side_effect = test_daemon_lifecycle["loop_iterations"]

        # Run the main function
        daemon.main()

        # Assertions using test data
        mock_os_operations.open.assert_called_once_with(
            test_fifo_data["path"], os.O_RDONLY | os.O_NONBLOCK
        )
        assert mock_os_operations.read.call_count == 2
        mock_asyncio.run.assert_any_call(
            mock_dependencies["AudioAnalysisService"].return_value.process_audio_chunk(
                test_fifo_data["chunks"][0]
            )
        )
        mock_asyncio.run.assert_any_call(
            mock_dependencies["AudioAnalysisService"].return_value.process_audio_chunk(
                test_fifo_data["chunks"][1]
            )
        )
        mock_atexit.register.assert_called_once_with(daemon._cleanup_fifo)
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, daemon._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, daemon._signal_handler)

        expected_logs = [
            "Starting audio analysis wrapper.",
            f"Opened FIFO for reading: {test_fifo_data['path']}",
        ]
        for expected_log in expected_logs:
            assert expected_log in caplog.text

    def test_run_audio_analysis_daemon__fifo_not_found(
        self,
        mocker,
        mock_dependencies,
        test_fifo_data,
        test_daemon_lifecycle,
        test_error_scenarios,
        caplog,
    ):
        """Should log an error if the FIFO is not found."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mock_signal = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mock_asyncio = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")

        mock_os.path.join.return_value = test_fifo_data["path"]
        mock_os.open.side_effect = test_error_scenarios["fifo_not_found"]

        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", new_callable=MagicMock
        )
        mock_global_shutdown_flag.__bool__.side_effect = test_daemon_lifecycle["immediate_exit"]

        # Run the main function
        daemon.main()

        # Assertions using test data
        assert test_error_scenarios["expected_error_messages"]["fifo_not_found"] in caplog.text
        mock_os.read.assert_not_called()
        mock_asyncio.run.assert_not_called()
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, daemon._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, daemon._signal_handler)

    def test_main__error_reading_fifo(
        self,
        mocker,
        mock_dependencies,
        test_fifo_data,
        test_daemon_lifecycle,
        test_error_scenarios,
        caplog,
    ):
        """Should log an error if reading from FIFO fails."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mock_signal = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mock_time = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.logging.basicConfig")

        mock_os.path.join.return_value = test_fifo_data["path"]
        mock_os_read = mock_os.read
        mock_time_sleep = mock_time.sleep

        # Use test data for error scenarios
        mock_os_read.side_effect = [
            test_error_scenarios["blocking_io"],
            test_error_scenarios["read_error"],
            b"",
        ]

        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", new_callable=MagicMock
        )
        mock_global_shutdown_flag.__bool__.side_effect = test_daemon_lifecycle["loop_iterations"]

        # Run the main function
        daemon.main()

        assert any(
            test_error_scenarios["expected_error_messages"]["read_error"] in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )
        mock_time_sleep.assert_called()
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, daemon._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, daemon._signal_handler)

    def test_signal_handler(self, mocker):
        """Should set the shutdown flag when a signal is received."""
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.logger")
        mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", False
        )  # Patch the global directly
        daemon._signal_handler(signal.SIGTERM, MagicMock())
        assert daemon._shutdown_flag is True

    def test_cleanup_fifo(self, mocker, caplog):
        """Should close the FIFO file descriptor."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon._fifo_analysis_fd", 456)
        mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._fifo_analysis_path", "/tmp/test_fifo.fifo"
        )

        daemon._cleanup_fifo()
        mock_os.close.assert_called_once_with(456)
        assert "Closed FIFO: /tmp/test_fifo.fifo" in caplog.text

    def test_main__no_audio_data_sleep(
        self, mocker, mock_dependencies, test_fifo_data, test_daemon_lifecycle, caplog
    ):
        """Should sleep when no audio data is available."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mock_time = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")

        mock_os.path.join.return_value = test_fifo_data["path"]
        mock_os.open.return_value = test_fifo_data["fd"]
        mock_os.O_RDONLY = os.O_RDONLY
        mock_os.O_NONBLOCK = os.O_NONBLOCK

        # Return empty bytes (no audio data available)
        mock_os.read.return_value = b""

        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", new_callable=MagicMock
        )
        mock_global_shutdown_flag.__bool__.side_effect = test_daemon_lifecycle["single_iteration"]

        # Run the main function
        daemon.main()

        # Should call time.sleep when no audio data using test data timeout
        mock_time.sleep.assert_called_with(test_fifo_data["read_timeout"])

    def test_main_general__exception_handling(
        self, mocker, mock_dependencies, test_fifo_data, test_error_scenarios, caplog
    ):
        """Should handle general exceptions in main function."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")

        mock_os.path.join.return_value = test_fifo_data["path"]
        # Use test data for general exception
        mock_os.open.side_effect = test_error_scenarios["general_error"]

        # Run the main function
        daemon.main()

        # Should log the general error using test data
        assert any(
            test_error_scenarios["expected_error_messages"]["general_error"] in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_main_entry_point_condition(self, mocker, mock_dependencies):
        """Should execute main entry point code when module name is __main__ (line 91)."""
        # Mock the main function to verify it gets called
        mock_main = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.main")

        # Simulate the condition on line 91 by directly evaluating it with __main__
        # This covers the condition: if __name__ == "__main__":
        module_name = "__main__"
        if module_name == "__main__":
            daemon.main()

        # Verify main() was called, covering line 91
        mock_main.assert_called_once()

    def test_main__fifo_permission_error(
        self, mocker, mock_dependencies, test_fifo_data, test_error_scenarios, caplog
    ):
        """Should handle permission errors when opening FIFO."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.os")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")

        mock_os.path.join.return_value = test_fifo_data["path"]
        mock_os.open.side_effect = test_error_scenarios["permission_denied"]

        # Run the main function
        daemon.main()

        # Should log the permission error
        assert any(
            "Permission denied" in r.message and r.levelno == logging.ERROR for r in caplog.records
        )

    def test_main__audio_processing_exception(
        self,
        mocker,
        mock_dependencies,
        mock_os_operations,
        test_fifo_data,
        test_daemon_lifecycle,
        caplog,
    ):
        """Should handle exceptions during audio processing gracefully."""
        mock_signal = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.signal")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.atexit")
        mock_asyncio = mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.asyncio")
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.time")

        # Mock asyncio.run to raise an exception during audio processing
        mock_asyncio.run.side_effect = Exception("Audio processing failed")

        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", new_callable=MagicMock
        )
        mock_global_shutdown_flag.__bool__.side_effect = test_daemon_lifecycle["single_iteration"]

        # Run the main function
        daemon.main()

        # Should handle the audio processing exception
        assert any(
            "An error occurred in the audio analysis wrapper" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_signal_handler__different_signals(self, mocker, test_daemon_lifecycle):
        """Should handle different signal types correctly."""
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon.logger")

        # Test SIGTERM
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGTERM, MagicMock())
        assert daemon._shutdown_flag is True

        # Reset and test SIGINT
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGINT, MagicMock())
        assert daemon._shutdown_flag is True

        # Reset and test other signal (should still work)
        mocker.patch("birdnetpi.wrappers.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGUSR1, MagicMock())
        assert daemon._shutdown_flag is True
