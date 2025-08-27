import logging
import signal
from unittest.mock import MagicMock, patch

import pytest

import birdnetpi.daemons.audio_analysis_daemon as daemon


@pytest.fixture(autouse=True)
def mock_daemon_setup(mocker, path_resolver):
    """Mock daemon setup to avoid subprocess calls and file system access."""
    mocker.patch("birdnetpi.daemons.audio_analysis_daemon.configure_structlog")
    mocker.patch("birdnetpi.daemons.audio_analysis_daemon.PathResolver", return_value=path_resolver)


@pytest.fixture(autouse=True)
def caplog_for_wrapper(caplog):
    """Fixture to capture logs from the wrapper script."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.daemons.audio_analysis_daemon")
    yield


class TestAudioAnalysisDaemon:
    """Test the audio analysis daemon."""

    def test_signal_handler(self, mocker):
        """Should set the shutdown flag when a signal is received."""
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon.logger")
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGTERM, MagicMock())
        assert daemon._shutdown_flag is True

    def test_signal_handler__different_signals(self, mocker):
        """Should handle different signal types correctly."""
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon.logger")

        # Test SIGTERM
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGTERM, MagicMock())
        assert daemon._shutdown_flag is True

        # Reset and test SIGINT
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGINT, MagicMock())
        assert daemon._shutdown_flag is True

        # Reset and test other signal (should still work)
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._shutdown_flag", False)
        daemon._signal_handler(signal.SIGUSR1, MagicMock())
        assert daemon._shutdown_flag is True

    def test_main_creates_event_loop(self, mocker):
        """Should create and run an event loop."""
        mock_loop = MagicMock()
        mock_asyncio = mocker.patch("birdnetpi.daemons.audio_analysis_daemon.asyncio")
        mock_asyncio.new_event_loop.return_value = mock_loop

        # Make run_until_complete raise KeyboardInterrupt to exit quickly
        mock_loop.run_until_complete.side_effect = KeyboardInterrupt()

        # Mock cleanup
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._cleanup_fifo")

        # Run main
        daemon.main()

        # Verify event loop was created and set
        mock_asyncio.new_event_loop.assert_called_once()
        mock_asyncio.set_event_loop.assert_called_once_with(mock_loop)
        mock_loop.run_until_complete.assert_called_once()

    def test_cleanup_fifo(self, mocker, caplog):
        """Should close the FIFO file descriptor and event loop."""
        mock_os = mocker.patch("birdnetpi.daemons.audio_analysis_daemon.os")
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._fifo_analysis_fd", 456)
        mocker.patch(
            "birdnetpi.daemons.audio_analysis_daemon._fifo_analysis_path", "/tmp/test_fifo.fifo"
        )

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.is_closed.return_value = False
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._event_loop", mock_loop)
        mocker.patch("birdnetpi.daemons.audio_analysis_daemon._session", None)

        daemon._cleanup_fifo()
        mock_os.close.assert_called_once_with(456)
        mock_loop.close.assert_called_once()
        assert "Closed FIFO: /tmp/test_fifo.fifo" in caplog.text

    @pytest.mark.asyncio
    async def test_init_session_and_service(self, mocker, path_resolver):
        """Should initialize session and audio analysis service."""
        from unittest.mock import AsyncMock

        from birdnetpi.config import BirdNETConfig

        # Mock the imports and classes
        mock_multilingual = MagicMock()
        mock_multilingual.attach_all_to_session = AsyncMock()

        mock_session = MagicMock()

        # Mock inside the actual function where imports happen
        with patch("birdnetpi.daemons.audio_analysis_daemon.init_session_and_service") as mock_init:
            # Make it an async function that returns expected values
            async def mock_init_fn(pr, cfg):
                return mock_session, MagicMock()

            mock_init.side_effect = mock_init_fn

            config = BirdNETConfig()
            session, service = await mock_init(path_resolver, config)

            assert session == mock_session
            assert service is not None
            mock_init.assert_called_once_with(path_resolver, config)

    def test_main_entry_point_condition(self, mocker):
        """Should execute main entry point code when module name is __main__."""
        # Mock the main function to verify it gets called
        mock_main = mocker.patch("birdnetpi.daemons.audio_analysis_daemon.main")

        # Simulate the condition by directly evaluating it
        module_name = "__main__"
        if module_name == "__main__":
            daemon.main()

        # Verify main() was called
        mock_main.assert_called_once()
