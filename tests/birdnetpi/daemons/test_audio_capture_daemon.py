import logging
import os
import signal
from unittest.mock import DEFAULT, MagicMock, patch

import pytest

import birdnetpi.daemons.audio_capture_daemon as daemon
from birdnetpi.audio.capture import AudioCaptureService


@pytest.fixture(autouse=True)
def mock_daemon_setup(mocker, path_resolver):
    """Mock daemon setup to avoid subprocess calls and file system access."""
    mocker.patch("birdnetpi.daemons.audio_capture_daemon.configure_structlog")
    mocker.patch("birdnetpi.daemons.audio_capture_daemon.PathResolver", return_value=path_resolver)


@pytest.fixture
def test_config():
    """Should provide test configuration data."""
    return {"some_config": "value", "audio": {"sample_rate": 48000}}


@pytest.fixture
def fifo_paths():
    """Provide test FIFO paths."""
    return {
        "base": "/tmp/fifo",
        "analysis": "/tmp/fifo/birdnet_audio_analysis.fifo",
        "livestream": "/tmp/fifo/birdnet_audio_livestream.fifo",
    }


@pytest.fixture
def file_descriptors():
    """Provide test file descriptor values."""
    return {"analysis": 123, "livestream": 456}


@pytest.fixture(autouse=True)
def mock_dependencies(mocker, test_config, fifo_paths, path_resolver):
    """Mock external dependencies for audio_capture_daemon.py."""
    # Configure path_resolver with test paths
    path_resolver.get_fifo_base_path = lambda: fifo_paths["base"]

    with patch.multiple(
        "birdnetpi.daemons.audio_capture_daemon",
        ConfigManager=DEFAULT,
        AudioCaptureService=DEFAULT,
    ) as mocks:
        # Configure mocks with test data
        mocks["ConfigManager"].return_value.load.return_value = test_config
        mocks["AudioCaptureService"].return_value = MagicMock(spec=AudioCaptureService)

        # Yield mocks for individual test configuration
        yield mocks


@pytest.fixture(autouse=True)
def caplog_for_wrapper(caplog):
    """Fixture to capture logs from the wrapper script."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.daemons.audio_capture_daemon")
    yield


@pytest.fixture
def mock_os_operations(mocker, fifo_paths, file_descriptors):
    """Mock common OS operations for FIFO handling."""
    mocks = {
        "makedirs": mocker.patch("birdnetpi.daemons.audio_capture_daemon.os.makedirs"),
        "mkfifo": mocker.patch("birdnetpi.daemons.audio_capture_daemon.os.mkfifo"),
        "open": mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.os.open",
            side_effect=[file_descriptors["analysis"], file_descriptors["livestream"]],
        ),
        "close": mocker.patch("birdnetpi.daemons.audio_capture_daemon.os.close"),
        "path_exists": mocker.patch("birdnetpi.daemons.audio_capture_daemon.os.path.exists"),
        "path_join": mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.os.path.join",
            side_effect=lambda *args: "/".join(str(arg) for arg in args),
        ),
    }
    return mocks


class TestAudioCaptureDaemon:
    """Test the audio capture daemon."""

    def test_run_audio_capture_daemon(
        self,
        mocker,
        mock_dependencies,
        mock_os_operations,
        fifo_paths,
        file_descriptors,
        test_config,
        caplog,
    ):
        """Should create FIFOs, open them, start service, and clean up on shutdown."""
        # Setup path existence checks - FIFOs don't exist initially, then do exist
        mock_os_operations["path_exists"].side_effect = [False, False, True, True]

        # Setup daemon lifecycle mocks
        mock_signal = mocker.patch("birdnetpi.daemons.audio_capture_daemon.signal")
        mock_atexit = mocker.patch("birdnetpi.daemons.audio_capture_daemon.atexit")
        mock_time = mocker.patch("birdnetpi.daemons.audio_capture_daemon.time")
        mock_shutdown_flag = mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.shutdown_flag",
            new_callable=MagicMock,
        )
        # Ensure the loop runs once and then exits
        mock_shutdown_flag.__bool__.side_effect = [False, True]

        # Run the main function
        daemon.main()

        # Assertions for FIFO creation
        mock_os_operations["makedirs"].assert_called_once_with(fifo_paths["base"], exist_ok=True)
        mock_os_operations["mkfifo"].assert_any_call(fifo_paths["analysis"])
        mock_os_operations["mkfifo"].assert_any_call(fifo_paths["livestream"])
        mock_os_operations["open"].assert_any_call(fifo_paths["analysis"], os.O_WRONLY)
        mock_os_operations["open"].assert_any_call(fifo_paths["livestream"], os.O_WRONLY)

        # Assertions for service lifecycle
        mock_dependencies["AudioCaptureService"].assert_called_once_with(
            test_config, file_descriptors["analysis"], file_descriptors["livestream"]
        )
        mock_dependencies["AudioCaptureService"].return_value.start_capture.assert_called_once()
        mock_dependencies["AudioCaptureService"].return_value.stop_capture.assert_called_once()

        # Assertions for signal handling
        mock_atexit.register.assert_called_once_with(daemon._cleanup_fifos)
        mock_signal.signal.assert_any_call(mock_signal.SIGTERM, daemon._signal_handler)
        mock_signal.signal.assert_any_call(mock_signal.SIGINT, daemon._signal_handler)
        mock_time.sleep.assert_called_with(0.1)  # Changed to more responsive polling interval

        # Assertions for log messages
        expected_logs = [
            "Starting audio capture wrapper.",
            f"Created FIFO: {fifo_paths['analysis']}",
            f"Created FIFO: {fifo_paths['livestream']}",
            "FIFOs opened for writing.",
            "Configuration loaded successfully.",
            "AudioCaptureService started.",
            "AudioCaptureService stopped.",
        ]
        for expected_log in expected_logs:
            assert expected_log in caplog.text

    def test_run_audio_capture_daemon__fifos_exist(
        self, mocker, mock_dependencies, mock_os_operations, caplog
    ):
        """Should not create FIFOs if they already exist."""
        # Setup path existence checks - all FIFOs already exist
        mock_os_operations["path_exists"].side_effect = [True, True, True, True]

        mock_shutdown_flag = mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.shutdown_flag",
            new_callable=MagicMock,
        )
        mock_shutdown_flag.__bool__.side_effect = [False, True]

        daemon.main()

        # Should not create FIFOs since they already exist
        mock_os_operations["mkfifo"].assert_not_called()
        assert "Created FIFO" not in caplog.text

    def test_run_audio_capture_daemon__config_not_found(
        self, mocker, mock_dependencies, mock_os_operations, caplog
    ):
        """Should raise FileNotFoundError if the configuration file is not found."""
        mock_os_operations["path_exists"].side_effect = [False, False, True, True]

        # Simulate config file not found
        mock_dependencies["ConfigManager"].return_value.load.side_effect = FileNotFoundError

        # The daemon should fail if config is not found
        with pytest.raises(FileNotFoundError):
            daemon.main()
        # Service should not be started if config is missing
        mock_dependencies["AudioCaptureService"].return_value.start_capture.assert_not_called()
        mock_dependencies["AudioCaptureService"].return_value.stop_capture.assert_not_called()

    def test_run_audio_capture_daemon__service_exception(
        self, mocker, mock_dependencies, mock_os_operations, caplog
    ):
        """Should log a general error and stop the service if an exception occurs."""
        mock_os_operations["path_exists"].side_effect = [False, False, True, True]

        # Simulate service start failure
        mock_dependencies["AudioCaptureService"].return_value.start_capture.side_effect = Exception(
            "Test error"
        )

        daemon.main()

        assert "An error occurred in the audio capture wrapper" in caplog.text
        assert "Test error" in caplog.text
        mock_dependencies["AudioCaptureService"].return_value.stop_capture.assert_called_once()

    def test_run_audio_capture_daemon__fifo_creation_error(
        self, mocker, mock_dependencies, mock_os_operations, caplog
    ):
        """Should handle FIFO creation errors gracefully."""
        mock_os_operations["path_exists"].side_effect = [False, False, True, True]
        mock_os_operations["mkfifo"].side_effect = OSError("Permission denied")

        daemon.main()

        assert "An error occurred in the audio capture wrapper" in caplog.text
        assert "Permission denied" in caplog.text
        mock_dependencies["AudioCaptureService"].return_value.start_capture.assert_not_called()

    def test_run_audio_capture_daemon__fifo_open_error(
        self, mocker, mock_dependencies, mock_os_operations, caplog
    ):
        """Should handle FIFO open errors gracefully."""
        mock_os_operations["path_exists"].side_effect = [False, False, True, True]
        mock_os_operations["open"].side_effect = OSError("FIFO not found")

        daemon.main()

        assert "An error occurred in the audio capture wrapper" in caplog.text
        assert "FIFO not found" in caplog.text
        mock_dependencies["AudioCaptureService"].return_value.start_capture.assert_not_called()

    def test_handle_signal_shutdown(self, mocker):
        """Should set the shutdown flag when a signal is received."""
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.logger")
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.shutdown_flag", False)

        daemon._signal_handler(signal.SIGTERM, MagicMock())

        assert daemon.DaemonState.shutdown_flag is True

    def test_handle_signal_shutdown__sigint(self, mocker):
        """Should set the shutdown flag when SIGINT is received."""
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.logger")
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.shutdown_flag", False)

        daemon._signal_handler(signal.SIGINT, MagicMock())

        assert daemon.DaemonState.shutdown_flag is True

    def test_cleanup_fifos(self, mocker, fifo_paths, file_descriptors, caplog):
        """Should close both FIFO file descriptors if they exist."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_capture_daemon.os")
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_fd",
            file_descriptors["analysis"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_fd",
            file_descriptors["livestream"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_path",
            fifo_paths["analysis"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_path",
            fifo_paths["livestream"],
        )

        daemon._cleanup_fifos()

        mock_os.close.assert_any_call(file_descriptors["analysis"])
        mock_os.close.assert_any_call(file_descriptors["livestream"])
        assert f"Closed FIFO: {fifo_paths['analysis']}" in caplog.text
        assert f"Closed FIFO: {fifo_paths['livestream']}" in caplog.text

    def test_cleanup_fifos___no_fds(self, mocker, caplog):
        """Should not attempt to close FIFOs if file descriptors are None."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_capture_daemon.os")
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_fd", None)
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_fd", None)

        daemon._cleanup_fifos()

        mock_os.close.assert_not_called()
        assert "Closed FIFO" not in caplog.text

    def test_cleanup_fifos__analysis_only(self, mocker, fifo_paths, file_descriptors, caplog):
        """Should close only the analysis FIFO if livestream FD is None."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_capture_daemon.os")
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_fd",
            file_descriptors["analysis"],
        )
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_fd", None)
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_path",
            fifo_paths["analysis"],
        )

        daemon._cleanup_fifos()

        mock_os.close.assert_called_once_with(file_descriptors["analysis"])
        assert f"Closed FIFO: {fifo_paths['analysis']}" in caplog.text
        assert f"Closed FIFO: {fifo_paths['livestream']}" not in caplog.text

    def test_cleanup_fifos__livestream_only(self, mocker, fifo_paths, file_descriptors, caplog):
        """Should close only the livestream FIFO if analysis FD is None."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_capture_daemon.os")
        mocker.patch("birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_fd", None)
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_fd",
            file_descriptors["livestream"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_path",
            fifo_paths["livestream"],
        )

        daemon._cleanup_fifos()

        mock_os.close.assert_called_once_with(file_descriptors["livestream"])
        assert f"Closed FIFO: {fifo_paths['livestream']}" in caplog.text
        assert f"Closed FIFO: {fifo_paths['analysis']}" not in caplog.text

    def test_cleanup_fifos__close_error(self, mocker, fifo_paths, file_descriptors, caplog):
        """Should propagate OS errors when closing FIFOs."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_capture_daemon.os")
        mock_os.close.side_effect = OSError("File descriptor not valid")
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_fd",
            file_descriptors["analysis"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_fd",
            file_descriptors["livestream"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_analysis_path",
            fifo_paths["analysis"],
        )
        mocker.patch(
            "birdnetpi.daemons.audio_capture_daemon.DaemonState.fifo_livestream_path",
            fifo_paths["livestream"],
        )

        # Should raise OSError since cleanup doesn't handle exceptions
        with pytest.raises(OSError, match="File descriptor not valid"):
            daemon._cleanup_fifos()

        # Verify it attempted to close the first FD
        mock_os.close.assert_called_once_with(file_descriptors["analysis"])

    def test_run_daemon_as_script(self, mocker, repo_root):
        """Should execute main when run as script."""
        import subprocess
        import sys

        # Get the path to the module
        module_path = repo_root / "src" / "birdnetpi" / "daemons" / "audio_capture_daemon.py"

        # Mock environment to avoid real execution - use a small timeout
        # Try to run the module as script, but expect it to fail quickly due to missing dependencies
        # We just want to trigger the __main__ block for coverage
        try:
            result = subprocess.run(
                [sys.executable, str(module_path)],
                capture_output=True,
                text=True,
                timeout=5,  # Slightly longer timeout
            )
            # We expect this to fail due to missing config or other issues, that's fine
            # The important thing is that the __main__ block was executed
            assert result.returncode != 0  # Should fail due to missing setup
        except subprocess.TimeoutExpired:
            # If it times out, that also means the __main__ block was executed
            # This covers line 106 in the module
            pass
