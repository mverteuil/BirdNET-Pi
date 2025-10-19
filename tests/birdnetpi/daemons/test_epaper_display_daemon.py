"""Tests for e-paper display daemon."""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.daemons.epaper_display_daemon import DaemonState, _signal_handler, main, main_async
from birdnetpi.display.epaper import EPaperDisplayService


class TestEPaperDisplayDaemon:
    """Test the e-paper display daemon."""

    @pytest.fixture(autouse=True)
    def reset_daemon_state(self):
        """Reset daemon state before each test."""
        DaemonState.reset()
        yield
        DaemonState.reset()

    def test_daemon_state_reset(self):
        """Should reset daemon state to initial values."""
        DaemonState.shutdown_flag = True
        DaemonState.reset()
        assert DaemonState.shutdown_flag is False

    def test_signal_handler(self):
        """Should set shutdown flag when signal is received."""
        assert DaemonState.shutdown_flag is False

        _signal_handler(signal.SIGTERM, None)

        assert DaemonState.shutdown_flag is True

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_main_async_starts_and_stops(self, path_resolver):
        """Should start service and handle shutdown gracefully."""
        mock_service = AsyncMock(spec=EPaperDisplayService)

        with (
            patch(
                "birdnetpi.daemons.epaper_display_daemon.PathResolver", return_value=path_resolver
            ),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.ConfigManager", autospec=True
            ) as mock_config_mgr,
            patch("birdnetpi.daemons.epaper_display_daemon.CoreDatabaseService", autospec=True),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.EPaperDisplayService",
                return_value=mock_service,
            ),
        ):
            # Configure mock config manager
            mock_config = MagicMock(spec=dict)
            mock_config_mgr.return_value.load.return_value = mock_config

            # Run main_async in a task
            task = asyncio.create_task(main_async())

            # Let it initialize
            await asyncio.sleep(0.1)

            # Trigger shutdown
            DaemonState.shutdown_flag = True

            # Wait for completion
            await asyncio.wait_for(task, timeout=2.0)

            # Verify service methods were called
            mock_service.stop.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_main_async_handles_service_exception(self, path_resolver):
        """Should handle service exceptions and still call stop."""
        mock_service = AsyncMock(spec=EPaperDisplayService)

        # Make start() raise an error, then set shutdown flag so daemon can exit
        async def failing_start():
            DaemonState.shutdown_flag = True
            raise RuntimeError("Service error")

        mock_service.start.side_effect = failing_start

        with (
            patch(
                "birdnetpi.daemons.epaper_display_daemon.PathResolver", return_value=path_resolver
            ),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.ConfigManager", autospec=True
            ) as mock_config_mgr,
            patch("birdnetpi.daemons.epaper_display_daemon.CoreDatabaseService", autospec=True),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.EPaperDisplayService",
                return_value=mock_service,
            ),
        ):
            # Configure mock config manager
            mock_config = MagicMock(spec=dict)
            mock_config_mgr.return_value.load.return_value = mock_config

            # Run main_async - should handle exception and call stop
            await main_async()

            # Verify stop was called even after error
            mock_service.stop.assert_called_once()

    def test_main_runs_and_handles_keyboard_interrupt(self, path_resolver):
        """Should handle KeyboardInterrupt gracefully."""
        mock_config = MagicMock(spec=dict)

        with (
            patch(
                "birdnetpi.daemons.epaper_display_daemon.PathResolver", return_value=path_resolver
            ),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.ConfigManager", autospec=True
            ) as mock_config_mgr,
            patch("birdnetpi.daemons.epaper_display_daemon.configure_structlog", autospec=True),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.asyncio.run", autospec=True
            ) as mock_asyncio_run,
        ):
            # Configure mock config manager
            mock_config_mgr.return_value.load.return_value = mock_config

            # Simulate KeyboardInterrupt
            mock_asyncio_run.side_effect = KeyboardInterrupt()

            # Should not raise exception
            main()

            # Verify asyncio.run was called
            mock_asyncio_run.assert_called_once()

    def test_main_runs_and_handles_exception(self, path_resolver):
        """Should handle exceptions gracefully."""
        mock_config = MagicMock(spec=dict)

        with (
            patch(
                "birdnetpi.daemons.epaper_display_daemon.PathResolver", return_value=path_resolver
            ),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.ConfigManager", autospec=True
            ) as mock_config_mgr,
            patch("birdnetpi.daemons.epaper_display_daemon.configure_structlog", autospec=True),
            patch(
                "birdnetpi.daemons.epaper_display_daemon.asyncio.run", autospec=True
            ) as mock_asyncio_run,
        ):
            # Configure mock config manager
            mock_config_mgr.return_value.load.return_value = mock_config

            # Simulate exception
            mock_asyncio_run.side_effect = RuntimeError("Test error")

            # Should not raise exception
            main()

            # Verify asyncio.run was called
            mock_asyncio_run.assert_called_once()
