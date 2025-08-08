import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

from birdnetpi.services.audio_websocket_service import AudioWebSocketService


@pytest.fixture
def mock_file_resolver():
    """Mock FilePathResolver for testing."""
    mock = MagicMock()
    mock.get_birdnetpi_config_path.return_value = "/mock/config.yaml"
    mock.get_fifo_base_path.return_value = "/mock/fifo"
    return mock


@pytest.fixture
def mock_config():
    """Mock BirdNETConfig for testing."""
    mock = MagicMock()
    mock.sample_rate = 44100
    mock.audio_channels = 1
    return mock


@pytest.fixture
def audio_websocket_service(mock_file_resolver, mock_config):
    """Create AudioWebSocketService instance for testing."""
    with patch(
        "birdnetpi.services.audio_websocket_service.FilePathResolver",
        return_value=mock_file_resolver,
    ):
        service = AudioWebSocketService("/mock/config.yaml", "/mock/fifo")
        return service


class TestAudioWebSocketService:
    """Test suite for AudioWebSocketService."""

    @pytest.mark.asyncio
    async def test_initialization(self, mock_file_resolver):
        """Should initialize service with correct paths."""
        with patch(
            "birdnetpi.services.audio_websocket_service.FilePathResolver",
            return_value=mock_file_resolver,
        ):
            service = AudioWebSocketService()

            assert service._shutdown_flag is False
            assert service._fifo_livestream_path == "/mock/fifo/birdnet_audio_livestream.fifo"
            assert service._audio_clients == set()
            assert service._processing_active is False

    @pytest.mark.asyncio
    async def test_websocket_handler_audio_path(self, audio_websocket_service):
        """Should handle audio websocket connections correctly."""
        mock_websocket = AsyncMock()
        mock_websocket.request.path = "/ws/audio"

        # Configure the websocket to be async iterable (empty iteration - immediate exit)
        mock_websocket.__aiter__.return_value = [].__iter__()

        await audio_websocket_service._websocket_handler(mock_websocket)

        # Websocket should have been added and removed
        assert mock_websocket not in audio_websocket_service._audio_clients

    @pytest.mark.asyncio
    async def test_websocket_handler_spectrogram_path(self, audio_websocket_service):
        """Should close spectrogram websocket connections with redirect message."""
        mock_websocket = MagicMock()
        mock_websocket.request.path = "/ws/spectrogram"
        mock_websocket.close = AsyncMock()

        await audio_websocket_service._websocket_handler(mock_websocket)

        mock_websocket.close.assert_called_once_with(
            code=4003, reason="Spectrogram moved to dedicated service"
        )

    @pytest.mark.asyncio
    async def test_websocket_handler_unknown_path(self, audio_websocket_service):
        """Should close unknown websocket connections."""
        mock_websocket = MagicMock()
        mock_websocket.request.path = "/unknown"
        mock_websocket.close = AsyncMock()

        await audio_websocket_service._websocket_handler(mock_websocket)

        mock_websocket.close.assert_called_once_with(code=4004, reason="Unknown endpoint")

    @pytest.mark.asyncio
    async def test_broadcast_audio_data(self, audio_websocket_service):
        """Should broadcast audio data to connected clients."""
        # Setup mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
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
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
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
            patch(
                "birdnetpi.services.audio_websocket_service.ConfigFileParser"
            ) as mock_config_parser,
            patch(
                "birdnetpi.services.audio_websocket_service.os.open", return_value=123
            ) as mock_open,
            patch("birdnetpi.services.audio_websocket_service.serve") as mock_serve,
            patch("birdnetpi.services.audio_websocket_service.signal"),
            patch("birdnetpi.services.audio_websocket_service.atexit"),
            patch(
                "birdnetpi.services.audio_websocket_service.asyncio.create_task"
            ) as mock_create_task,
        ):
            mock_config_parser.return_value.load_config.return_value = mock_config
            mock_server = MagicMock()  # Regular mock, not AsyncMock

            # Mock serve to return an awaitable
            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func

            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            await audio_websocket_service.start()

            # Verify configuration was loaded
            mock_config_parser.assert_called_once_with("/mock/config.yaml")
            mock_config_parser.return_value.load_config.assert_called_once()

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

            # Verify task was created
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_fifo_not_found(self, audio_websocket_service, mock_config):
        """Should raise exception when FIFO not found."""
        with (
            patch(
                "birdnetpi.services.audio_websocket_service.ConfigFileParser"
            ) as mock_config_parser,
            patch(
                "birdnetpi.services.audio_websocket_service.os.open", side_effect=FileNotFoundError
            ),
        ):
            mock_config_parser.return_value.load_config.return_value = mock_config

            with pytest.raises(FileNotFoundError):
                await audio_websocket_service.start()

    @pytest.mark.asyncio
    async def test_stop(self, audio_websocket_service):
        """Should stop service and clean up resources."""
        # Setup mock resources
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._websocket_server = MagicMock()

        # Create a real asyncio task that we can cancel
        async def dummy_fifo_loop():
            while True:
                await asyncio.sleep(0.1)

        task = asyncio.create_task(dummy_fifo_loop())
        audio_websocket_service._fifo_task = task

        with patch("birdnetpi.services.audio_websocket_service.os.close") as mock_close:
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
