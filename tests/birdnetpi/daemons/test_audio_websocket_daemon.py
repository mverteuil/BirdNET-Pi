from unittest.mock import AsyncMock, patch

import pytest

import birdnetpi.daemons.audio_websocket_daemon as daemon


@pytest.fixture(autouse=True)
def mock_daemon_setup(mocker, path_resolver):
    """Mock daemon setup to avoid subprocess calls and file system access."""
    mocker.patch("birdnetpi.daemons.audio_websocket_daemon.configure_structlog")
    mocker.patch(
        "birdnetpi.daemons.audio_websocket_daemon.PathResolver", return_value=path_resolver
    )


class TestAudioWebsocketDaemon:
    """Test the audio websocket daemon wrapper."""

    @pytest.mark.asyncio
    async def test_main_async_successful_run(self):
        """Should create service, start it, wait for shutdown, and stop it."""
        mock_service = AsyncMock()

        with patch(
            "birdnetpi.daemons.audio_websocket_daemon.AudioWebSocketService",
            return_value=mock_service,
        ) as mock_service_class:
            await daemon.main_async()

            # Verify service was created
            mock_service_class.assert_called_once()

            # Verify service lifecycle methods were called
            mock_service.start.assert_called_once()
            mock_service.wait_for_shutdown.assert_called_once()
            mock_service.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_async_service_start_failure(self):
        """Should handle service start failure and still call stop."""
        mock_service = AsyncMock()
        mock_service.start.side_effect = Exception("Start failed")

        with patch(
            "birdnetpi.daemons.audio_websocket_daemon.AudioWebSocketService",
            return_value=mock_service,
        ):
            await daemon.main_async()

            # Verify start was attempted and stop was still called
            mock_service.start.assert_called_once()
            mock_service.stop.assert_called_once()
            # wait_for_shutdown should not be called due to exception
            mock_service.wait_for_shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_main_async_wait_for_shutdown_failure(self):
        """Should handle wait for shutdown failure and still call stop."""
        mock_service = AsyncMock()
        mock_service.wait_for_shutdown.side_effect = Exception("Wait failed")

        with patch(
            "birdnetpi.daemons.audio_websocket_daemon.AudioWebSocketService",
            return_value=mock_service,
        ):
            await daemon.main_async()

            # Verify all methods were called
            mock_service.start.assert_called_once()
            mock_service.wait_for_shutdown.assert_called_once()
            mock_service.stop.assert_called_once()

    def test_main_keyboard_interrupt(self):
        """Should handle keyboard interrupt gracefully."""

        def mock_run(coro):
            # Consume the coroutine to avoid warning
            coro.close()
            raise KeyboardInterrupt

        with patch("birdnetpi.daemons.audio_websocket_daemon.asyncio.run", side_effect=mock_run):
            # Should not raise exception
            daemon.main()

    def test_main_general_exception(self):
        """Should handle general exceptions gracefully."""

        def mock_run(coro):
            # Consume the coroutine to avoid warning
            coro.close()
            raise Exception("General error")

        with patch(
            "birdnetpi.daemons.audio_websocket_daemon.asyncio.run",
            side_effect=mock_run,
        ):
            # Should not raise exception
            daemon.main()
