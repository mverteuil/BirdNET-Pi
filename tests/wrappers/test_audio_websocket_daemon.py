import logging
import os
import signal
from unittest.mock import DEFAULT, MagicMock, patch

import pytest

import birdnetpi.wrappers.audio_websocket_daemon as daemon
from birdnetpi.services.audio_websocket_service import AudioWebSocketService


@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    """Mock external dependencies for audio_websocket_daemon.py."""
    with patch.multiple(
        "birdnetpi.wrappers.audio_websocket_daemon",
        FilePathResolver=DEFAULT,
        ConfigFileParser=DEFAULT,
        AudioWebSocketService=DEFAULT,
    ) as mocks:
        # Configure mocks
        mocks["FilePathResolver"].return_value.get_fifo_base_path.return_value = "/tmp/fifo"
        mocks[
            "FilePathResolver"
        ].return_value.get_birdnet_pi_config_path.return_value = "/tmp/config.yaml"
        mocks["ConfigFileParser"].return_value.load_config.return_value = {
            "sample_rate": 44100,
            "audio_channels": 1,
        }
        mocks["AudioWebSocketService"].return_value = MagicMock(spec=AudioWebSocketService)

        # Yield mocks for individual test configuration
        yield mocks


@pytest.fixture(autouse=True)
def caplog_for_wrapper(caplog):
    """Fixture to capture logs from the wrapper script."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.wrappers.audio_websocket_daemon")
    yield


class TestAudioWebsocketDaemon:
    """Test the audio websocket daemon."""

    def test_main_successful_run(self, mocker, mock_dependencies, caplog):
        """Should open FIFO, read data, stream, and clean up on shutdown."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.os")
        mock_signal = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.signal")
        mock_atexit = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.atexit")
        mock_time = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.time")
        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_websocket_daemon._shutdown_flag", new_callable=MagicMock
        )

        mock_os.path.join.return_value = "/tmp/fifo/birdnet_audio_livestream.fifo"
        mock_os.open.return_value = 789  # Mock file descriptor
        mock_os.O_RDONLY = os.O_RDONLY
        mock_os.O_NONBLOCK = os.O_NONBLOCK

        mock_os.read.side_effect = [b"audio_chunk_1", b"audio_chunk_2", b"", b""]

        mock_global_shutdown_flag.__bool__.side_effect = [False, False, False, True]

        daemon.main()

        mock_os.open.assert_called_once_with(
            "/tmp/fifo/birdnet_audio_livestream.fifo", os.O_RDONLY | os.O_NONBLOCK
        )
        mock_dependencies["AudioWebSocketService"].assert_called_once_with(44100, 1)
        # AudioWebSocketService doesn't have start/stop methods, only stream_audio_chunk
        # The daemon calls asyncio.run(service.stream_audio_chunk()) for each chunk
        mock_atexit.register.assert_called_once_with(daemon._cleanup_fifo_and_service)
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, daemon._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, daemon._signal_handler)
        mock_time.sleep.assert_called_with(0.01)

        assert "Starting audio websocket wrapper." in caplog.text
        assert "Opened FIFO for reading: /tmp/fifo/birdnet_audio_livestream.fifo" in caplog.text
        assert "Configuration loaded successfully." in caplog.text

    def test_main_fifo_not_found(self, mocker, mock_dependencies, caplog):
        """Should log an error if the FIFO is not found."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.os")
        mock_os.path.join.return_value = "/tmp/fifo/birdnet_audio_livestream.fifo"
        mock_os.open.side_effect = FileNotFoundError

        daemon.main()

        assert (
            "FIFO not found at /tmp/fifo/birdnet_audio_livestream.fifo. "
            "Ensure audio_capture is running and creating it." in caplog.text
        )
        # AudioWebSocketService should not be called since FIFO opening failed
        mock_dependencies["AudioWebSocketService"].assert_not_called()

    def test_main_general_exception(self, mocker, mock_dependencies, caplog):
        """Should log a general error and stop the service if an exception occurs."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.os")
        mock_os.path.join.return_value = "/tmp/fifo/birdnet_audio_livestream.fifo"
        mock_os.open.return_value = 789
        mock_os.read.side_effect = Exception("Test error")

        mock_global_shutdown_flag = mocker.patch(
            "birdnetpi.wrappers.audio_websocket_daemon._shutdown_flag", new_callable=MagicMock
        )
        mock_global_shutdown_flag.__bool__.side_effect = [False, False, True]

        daemon.main()

        assert "Error reading from FIFO or streaming to WebSocket: Test error" in caplog.text

    def test_signal_handler(self, mocker):
        """Should set the shutdown flag when a signal is received."""
        mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.logger")
        mocker.patch("birdnetpi.wrappers.audio_websocket_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGTERM, MagicMock())
        assert daemon._shutdown_flag is True

    def test_cleanup_fifo_and_service(self, mocker, caplog):
        """Should close the FIFO and stop the service during cleanup."""
        mock_os = mocker.patch("birdnetpi.wrappers.audio_websocket_daemon.os")
        # Set the global _fifo_livestream_fd to an integer value, simulating os.open
        daemon._fifo_livestream_fd = 789
        mocker.patch(
            "birdnetpi.wrappers.audio_websocket_daemon._fifo_livestream_path",
            "/tmp/fifo/livestream.fifo",
        )
        daemon._cleanup_fifo_and_service()

        mock_os.close.assert_called_once_with(789)
        # AudioWebSocketService doesn't need explicit cleanup, connections handle themselves
        assert "Closed FIFO: /tmp/fifo/livestream.fifo" in caplog.text
        assert daemon._fifo_livestream_fd is None
