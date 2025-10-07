import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets
from websockets import Request
from websockets.asyncio.server import Server, ServerConnection

from birdnetpi.audio.websocket import AudioWebSocketService
from birdnetpi.config.models import BirdNETConfig


@pytest.fixture
def mock_config():
    """Mock BirdNETConfig for testing."""
    mock = MagicMock(spec=BirdNETConfig)
    mock.sample_rate = 44100
    mock.audio_channels = 1
    return mock


@pytest.fixture
def audio_websocket_service(path_resolver, mock_config):
    """Create AudioWebSocketService instance for testing."""
    # Customize the global path_resolver for this test
    path_resolver.get_birdnetpi_config_path = lambda: "/mock/config.yaml"
    path_resolver.get_fifo_base_path = lambda: "/mock/fifo"

    service = AudioWebSocketService(path_resolver)
    return service


class TestAudioWebSocketService:
    """Test suite for AudioWebSocketService."""

    @pytest.mark.asyncio
    async def test_initialization(self, path_resolver):
        """Should initialize service with correct paths."""
        # Customize the global path_resolver for this test
        path_resolver.get_birdnetpi_config_path = lambda: "/mock/config.yaml"
        path_resolver.get_fifo_base_path = lambda: "/mock/fifo"

        service = AudioWebSocketService(path_resolver)

        assert service._shutdown_flag is False
        assert service._fifo_livestream_path == "/mock/fifo/birdnet_audio_livestream.fifo"
        assert service._audio_clients == set()
        assert service._processing_active is False

    @pytest.mark.asyncio
    async def test_websocket_handler_audio_path(self, audio_websocket_service):
        """Should handle audio websocket connections correctly."""
        # Create mock without spec to allow dynamic attribute setting
        mock_websocket = AsyncMock(spec=ServerConnection)
        # Configure request mock with path
        mock_request = MagicMock(spec=Request)
        mock_request.path = "/ws/audio"
        mock_websocket.request = mock_request

        # Configure the websocket to be async iterable (empty iteration - immediate exit)
        mock_websocket.__aiter__.return_value = [].__iter__()

        await audio_websocket_service._websocket_handler(mock_websocket)

        # Websocket should have been added and removed
        assert mock_websocket not in audio_websocket_service._audio_clients

    @pytest.mark.asyncio
    async def test_websocket_handler_unknown_path(self, audio_websocket_service):
        """Should close unknown websocket connections."""
        # Create mock without spec to allow dynamic attribute setting
        mock_websocket = AsyncMock(spec=ServerConnection)
        # Configure request mock with path
        mock_request = MagicMock(spec=Request)
        mock_request.path = "/unknown"
        mock_websocket.request = mock_request

        await audio_websocket_service._websocket_handler(mock_websocket)

        mock_websocket.close.assert_called_once_with(code=4004, reason="Unknown endpoint")

    @pytest.mark.asyncio
    async def test_broadcast_audio_data(self, audio_websocket_service):
        """Should broadcast audio data to connected clients."""
        # Setup mock clients
        mock_client1 = AsyncMock(spec=ServerConnection)
        mock_client2 = AsyncMock(spec=ServerConnection)
        audio_websocket_service._audio_clients.add(mock_client1)
        audio_websocket_service._audio_clients.add(mock_client2)

        audio_data = b"test_audio_data"
        await audio_websocket_service._broadcast_audio_data(audio_data)

        # Check that data was sent to both clients
        expected_header = len(audio_data).to_bytes(4, byteorder="little")
        expected_packet = expected_header + audio_data

        mock_client1.send.assert_called_once_with(expected_packet)
        mock_client2.send.assert_called_once_with(expected_packet)

    @pytest.mark.asyncio
    async def test_broadcast_audio_data_removes_disconnected_clients(self, audio_websocket_service):
        """Should remove disconnected clients during broadcast."""
        # Setup mock clients
        mock_client1 = AsyncMock(spec=ServerConnection)
        mock_client2 = AsyncMock(spec=ServerConnection)
        mock_client2.send.side_effect = websockets.exceptions.ConnectionClosed(None, None)

        audio_websocket_service._audio_clients.add(mock_client1)
        audio_websocket_service._audio_clients.add(mock_client2)

        audio_data = b"test_audio_data"
        await audio_websocket_service._broadcast_audio_data(audio_data)

        # Client 2 should be removed from the set
        assert mock_client1 in audio_websocket_service._audio_clients
        assert mock_client2 not in audio_websocket_service._audio_clients

    @pytest.mark.asyncio
    async def test_start(self, audio_websocket_service, mock_config):
        """Should start service successfully."""
        with (
            patch("birdnetpi.audio.websocket.os.open", return_value=123) as mock_open,
            patch("birdnetpi.audio.websocket.serve", autospec=True) as mock_serve,
            patch("birdnetpi.audio.websocket.signal", autospec=True),
            patch("birdnetpi.audio.websocket.atexit", autospec=True),
        ):
            mock_server = MagicMock(spec=Server)  # Regular mock, not AsyncMock

            # Mock serve to return an awaitable
            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func

            await audio_websocket_service.start()

            # Verify FIFO was opened
            mock_open.assert_called_once_with(
                "/mock/fifo/birdnet_audio_livestream.fifo", os.O_RDONLY | os.O_NONBLOCK
            )

            # Verify WebSocket server was started
            mock_serve.assert_called_once_with(
                audio_websocket_service._websocket_handler,
                "0.0.0.0",
                9001,
                logger=mock_serve.call_args[1]["logger"],
            )

            # Verify FIFO task was created (it's stored as an attribute)
            assert audio_websocket_service._fifo_task is not None

    @pytest.mark.asyncio
    async def test_start_fifo_not_found(self, audio_websocket_service, mock_config):
        """Should raise exception when FIFO not found."""
        with patch("birdnetpi.audio.websocket.os.open", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                await audio_websocket_service.start()

    @pytest.mark.asyncio
    async def test_stop(self, audio_websocket_service):
        """Should stop service and clean up resources."""
        # Setup mock resources
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._websocket_server = MagicMock(spec=Server)

        # Create a real asyncio task that we can cancel
        async def dummy_fifo_loop():
            while True:
                await asyncio.sleep(0.1)

        task = asyncio.create_task(dummy_fifo_loop())
        audio_websocket_service._fifo_task = task

        with patch("birdnetpi.audio.websocket.os.close", autospec=True) as mock_close:
            await audio_websocket_service.stop()

            # Verify shutdown flag is set
            assert audio_websocket_service._shutdown_flag is True

            # Verify task was cancelled
            assert task.cancelled()

            # Verify cleanup was called
            mock_close.assert_called_once_with(123)
            audio_websocket_service._websocket_server.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_shutdown(self, audio_websocket_service):
        """Should wait until shutdown flag is set."""
        # Start the wait in background
        wait_task = asyncio.create_task(audio_websocket_service.wait_for_shutdown())

        # Let it wait briefly
        await asyncio.sleep(0.01)

        # Set shutdown flag
        audio_websocket_service._shutdown_flag = True

        # Should complete now
        await asyncio.wait_for(wait_task, timeout=0.1)
