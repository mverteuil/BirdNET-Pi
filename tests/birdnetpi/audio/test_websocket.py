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
    mock = MagicMock(spec=BirdNETConfig, sample_rate=44100, audio_channels=1)
    return mock


@pytest.fixture
def audio_websocket_service(path_resolver, mock_config):
    """Create AudioWebSocketService instance for testing."""
    path_resolver.get_birdnetpi_config_path = lambda: "/mock/config.yaml"
    path_resolver.get_fifo_base_path = lambda: "/mock/fifo"
    service = AudioWebSocketService(path_resolver)
    return service


class TestAudioWebSocketService:
    """Test suite for AudioWebSocketService."""

    @pytest.mark.asyncio
    async def test_initialization(self, path_resolver):
        """Should initialize service with correct paths."""
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
        mock_websocket = AsyncMock(spec=ServerConnection)
        mock_request = MagicMock(spec=Request)
        mock_request.path = "/ws/audio"
        mock_websocket.request = mock_request
        mock_websocket.__aiter__.return_value = [].__iter__()
        await audio_websocket_service._websocket_handler(mock_websocket)
        assert mock_websocket not in audio_websocket_service._audio_clients

    @pytest.mark.asyncio
    async def test_websocket_handler_unknown_path(self, audio_websocket_service):
        """Should close unknown websocket connections."""
        mock_websocket = AsyncMock(spec=ServerConnection)
        mock_request = MagicMock(spec=Request)
        mock_request.path = "/unknown"
        mock_websocket.request = mock_request
        await audio_websocket_service._websocket_handler(mock_websocket)
        mock_websocket.close.assert_called_once_with(code=4004, reason="Unknown endpoint")

    @pytest.mark.asyncio
    async def test_broadcast_audio_data(self, audio_websocket_service):
        """Should broadcast audio data to connected clients."""
        mock_client1 = AsyncMock(spec=ServerConnection)
        mock_client2 = AsyncMock(spec=ServerConnection)
        audio_websocket_service._audio_clients.add(mock_client1)
        audio_websocket_service._audio_clients.add(mock_client2)
        audio_data = b"test_audio_data"
        await audio_websocket_service._broadcast_audio_data(audio_data)
        expected_header = len(audio_data).to_bytes(4, byteorder="little")
        expected_packet = expected_header + audio_data
        mock_client1.send.assert_called_once_with(expected_packet)
        mock_client2.send.assert_called_once_with(expected_packet)

    @pytest.mark.asyncio
    async def test_broadcast_audio_data_removes_disconnected_clients(self, audio_websocket_service):
        """Should remove disconnected clients during broadcast."""
        mock_client1 = AsyncMock(spec=ServerConnection)
        mock_client2 = AsyncMock(spec=ServerConnection)
        mock_client2.send.side_effect = websockets.exceptions.ConnectionClosed(None, None)
        audio_websocket_service._audio_clients.add(mock_client1)
        audio_websocket_service._audio_clients.add(mock_client2)
        audio_data = b"test_audio_data"
        await audio_websocket_service._broadcast_audio_data(audio_data)
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
            mock_server = MagicMock(spec=Server)

            async def mock_serve_func(*args, **kwargs):
                return mock_server

            mock_serve.side_effect = mock_serve_func
            await audio_websocket_service.start()
            mock_open.assert_called_once_with(
                "/mock/fifo/birdnet_audio_livestream.fifo", os.O_RDONLY | os.O_NONBLOCK
            )
            mock_serve.assert_called_once_with(
                audio_websocket_service._websocket_handler,
                "0.0.0.0",
                9001,
                logger=mock_serve.call_args[1]["logger"],
            )
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
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._websocket_server = MagicMock(spec=Server)

        async def dummy_fifo_loop():
            while True:
                await asyncio.sleep(0.1)

        task = asyncio.create_task(dummy_fifo_loop())
        audio_websocket_service._fifo_task = task
        with patch("birdnetpi.audio.websocket.os.close", autospec=True) as mock_close:
            await audio_websocket_service.stop()
            assert audio_websocket_service._shutdown_flag is True
            assert task.cancelled()
            mock_close.assert_called_once_with(123)
            audio_websocket_service._websocket_server.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_shutdown(self, audio_websocket_service):
        """Should wait until shutdown flag is set."""
        wait_task = asyncio.create_task(audio_websocket_service.wait_for_shutdown())
        await asyncio.sleep(0.01)
        audio_websocket_service._shutdown_flag = True
        await asyncio.wait_for(wait_task, timeout=0.1)

    @pytest.mark.asyncio
    async def test_extract_websocket_path_with_request_line_fallback(self, audio_websocket_service):
        """Should extract path from request line when path attribute not available."""
        mock_websocket = AsyncMock(spec=ServerConnection)

        # Create a simple object that has a string representation but no path attribute
        class MockRequest:
            def __str__(self):
                return "GET /ws/audio HTTP/1.1"

        mock_websocket.request = MockRequest()

        path = await audio_websocket_service._extract_websocket_path(mock_websocket)
        assert path == "/ws/audio"

    @pytest.mark.asyncio
    async def test_extract_websocket_path_defaults_to_root_on_error(self, audio_websocket_service):
        """Should default to root path when extraction fails."""
        mock_websocket = AsyncMock(spec=ServerConnection)

        # Create a request with malformed string representation
        class MockRequest:
            def __str__(self):
                return "malformed"

        mock_websocket.request = MockRequest()

        path = await audio_websocket_service._extract_websocket_path(mock_websocket)
        assert path == "/"

    @pytest.mark.asyncio
    async def test_extract_websocket_path_handles_exception(self, audio_websocket_service):
        """Should handle exceptions during path extraction and default to root."""
        mock_websocket = AsyncMock(spec=ServerConnection)
        mock_websocket.request = None  # Will cause AttributeError

        path = await audio_websocket_service._extract_websocket_path(mock_websocket)
        assert path == "/"

    @pytest.mark.asyncio
    async def test_broadcast_audio_data_handles_general_exception(self, audio_websocket_service):
        """Should handle general exceptions during broadcast."""
        mock_client = AsyncMock(spec=ServerConnection)
        mock_client.send.side_effect = RuntimeError("Test error")
        audio_websocket_service._audio_clients.add(mock_client)
        audio_data = b"test_data"

        # Should not raise, but log the error
        await audio_websocket_service._broadcast_audio_data(audio_data)

    @pytest.mark.asyncio
    async def test_broadcast_audio_data_with_no_clients(self, audio_websocket_service):
        """Should handle broadcast when no clients are connected."""
        audio_data = b"test_data"
        # No clients added, should not raise
        await audio_websocket_service._broadcast_audio_data(audio_data)

    @pytest.mark.asyncio
    async def test_fifo_reading_loop_without_fifo_fd(self, audio_websocket_service):
        """Should handle FIFO reading loop when FIFO is not open."""
        audio_websocket_service._fifo_livestream_fd = None
        audio_websocket_service._shutdown_flag = False

        # Run one iteration and then shut down
        async def delayed_shutdown():
            await asyncio.sleep(0.05)
            audio_websocket_service._shutdown_flag = True

        shutdown_task = asyncio.create_task(delayed_shutdown())
        await audio_websocket_service._fifo_reading_loop()
        await shutdown_task

    @pytest.mark.asyncio
    async def test_fifo_reading_loop_blocking_io_error(self, audio_websocket_service):
        """Should handle BlockingIOError gracefully."""
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._shutdown_flag = False

        read_count = 0

        def mock_read(fd, size):
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                raise BlockingIOError
            audio_websocket_service._shutdown_flag = True
            return b""

        with patch("birdnetpi.audio.websocket.os.read", side_effect=mock_read):
            await audio_websocket_service._fifo_reading_loop()

        assert read_count == 2

    @pytest.mark.asyncio
    async def test_fifo_reading_loop_general_exception(self, audio_websocket_service):
        """Should handle general exceptions during FIFO reading."""
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._shutdown_flag = False

        read_count = 0

        def mock_read(fd, size):
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                raise RuntimeError("Test error")
            audio_websocket_service._shutdown_flag = True
            return b""

        with patch("birdnetpi.audio.websocket.os.read", side_effect=mock_read):
            await audio_websocket_service._fifo_reading_loop()

        assert read_count == 2

    @pytest.mark.asyncio
    async def test_fifo_reading_loop_broadcasts_when_clients_connected(
        self, audio_websocket_service
    ):
        """Should broadcast audio data when clients are connected."""
        audio_websocket_service._fifo_livestream_fd = 123
        audio_websocket_service._shutdown_flag = False
        mock_client = AsyncMock(spec=ServerConnection)
        audio_websocket_service._audio_clients.add(mock_client)

        read_count = 0

        def mock_read(fd, size):
            nonlocal read_count
            read_count += 1
            if read_count == 1:
                return b"audio_data"
            audio_websocket_service._shutdown_flag = True
            return b""

        with patch("birdnetpi.audio.websocket.os.read", side_effect=mock_read):
            await audio_websocket_service._fifo_reading_loop()

        # Verify audio was broadcast to the client
        assert mock_client.send.call_count == 1

    @pytest.mark.asyncio
    async def test_start_general_exception(self, audio_websocket_service):
        """Should handle general exceptions during start."""
        with patch("birdnetpi.audio.websocket.os.open", side_effect=RuntimeError("Test error")):
            with pytest.raises(RuntimeError, match="Test error"):
                await audio_websocket_service.start()

    @pytest.mark.asyncio
    async def test_handle_audio_websocket_connection_closed(self, audio_websocket_service):
        """Should handle connection closed exception gracefully."""
        mock_websocket = AsyncMock(spec=ServerConnection)

        # Configure the async iterator to raise ConnectionClosed
        mock_websocket.__aiter__.return_value.__anext__.side_effect = (
            websockets.exceptions.ConnectionClosed(None, None)
        )

        await audio_websocket_service._handle_audio_websocket(mock_websocket)

        assert mock_websocket not in audio_websocket_service._audio_clients

    @pytest.mark.asyncio
    async def test_signal_handler(self, audio_websocket_service):
        """Should set shutdown flag when signal received."""
        assert audio_websocket_service._shutdown_flag is False
        audio_websocket_service._signal_handler(15, None)
        assert audio_websocket_service._shutdown_flag is True

    @pytest.mark.asyncio
    async def test_cleanup_fifo_and_service_without_resources(self, audio_websocket_service):
        """Should handle cleanup when no resources are allocated."""
        # Both fd and server are None
        audio_websocket_service._fifo_livestream_fd = None
        audio_websocket_service._websocket_server = None

        # Should not raise
        audio_websocket_service._cleanup_fifo_and_service()
