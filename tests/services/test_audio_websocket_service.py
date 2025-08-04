import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import WebSocket
from pydub import AudioSegment

from birdnetpi.services.audio_websocket_service import AudioWebSocketService


@pytest.fixture
def audio_websocket_service():
    """Return an AudioWebSocketService instance for testing."""
    return AudioWebSocketService(samplerate=48000, channels=1)


@pytest.fixture(autouse=True)
def caplog_for_audio_websocket_service(caplog):
    """Fixture to capture logs from audio_websocket_service.py."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.services.audio_websocket_service")
    yield


class TestAudioWebSocketService:
    """Test the AudioWebSocketService class."""

    def test_init(self, audio_websocket_service):
        """Should initialize with correct attributes."""
        assert audio_websocket_service.samplerate == 48000
        assert audio_websocket_service.channels == 1
        assert audio_websocket_service.connected_websockets == set()

    async def test_connect_websocket(self, audio_websocket_service, caplog):
        """Should add a websocket to connected_websockets and log."""
        mock_websocket = AsyncMock(spec=WebSocket)
        await audio_websocket_service.connect_websocket(mock_websocket)
        assert mock_websocket in audio_websocket_service.connected_websockets
        assert "New WebSocket connected." in caplog.text

    async def test_disconnect_websocket(self, audio_websocket_service, caplog):
        """Should remove a websocket from connected_websockets and log."""
        mock_websocket = AsyncMock(spec=WebSocket)
        audio_websocket_service.connected_websockets.add(mock_websocket)
        await audio_websocket_service.disconnect_websocket(mock_websocket)
        assert mock_websocket not in audio_websocket_service.connected_websockets
        assert "WebSocket disconnected." in caplog.text

    @pytest.mark.asyncio
    async def test_stream_audio_chunk_no_connected_websockets(self, audio_websocket_service):
        """Should return early if no websockets are connected."""
        audio_websocket_service.connected_websockets.clear()
        with patch(
            "birdnetpi.services.audio_websocket_service.AudioSegment"
        ) as mock_audio_segment:
            await audio_websocket_service.stream_audio_chunk(b"test_audio")
            mock_audio_segment.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_audio_chunk_success(self, audio_websocket_service):
        """Should encode and stream audio to connected websockets."""
        mock_websocket = AsyncMock(spec=WebSocket)
        audio_websocket_service.connected_websockets.add(mock_websocket)

        mock_audio_segment_instance = MagicMock()
        
        # Mock the export method to write to the BytesIO buffer
        def mock_export(buffer, format=None):
            # Write the encoded audio to the buffer
            buffer.write(b"encoded_audio")
            return buffer
        
        mock_audio_segment_instance.export.side_effect = mock_export

        with patch(
            "birdnetpi.services.audio_websocket_service.AudioSegment.__new__",
            return_value=mock_audio_segment_instance,
        ) as mock_audio_segment_new:
            # Use a numpy array to create valid int16 audio bytes
            raw_audio_np = np.zeros(48000, dtype=np.int16)  # 1 second of silence
            audio_data_bytes = raw_audio_np.tobytes()

            await audio_websocket_service.stream_audio_chunk(audio_data_bytes)

            mock_audio_segment_new.assert_called_once_with(
                AudioSegment,  # __new__ receives the class as its first argument
                audio_data_bytes,
                sample_width=2,
                frame_rate=audio_websocket_service.samplerate,
                channels=audio_websocket_service.channels,
            )
            # Verify export was called with a BytesIO object and format="mp3"
            mock_audio_segment_instance.export.assert_called_once()
            call_args = mock_audio_segment_instance.export.call_args
            assert hasattr(call_args[0][0], 'write')  # First arg should be BytesIO-like
            assert call_args[1] == {'format': 'mp3'}
            mock_websocket.send_bytes.assert_called_once_with(b"encoded_audio")

    @pytest.mark.asyncio
    async def test_stream_audio_chunk_error_sending_to_websocket(
        self, audio_websocket_service, caplog
    ):
        """Should log error and disconnect websocket if sending fails."""
        mock_websocket = AsyncMock(spec=WebSocket)
        mock_websocket.send_bytes.side_effect = Exception("Send error")
        audio_websocket_service.connected_websockets.add(mock_websocket)

        mock_audio_segment_instance = MagicMock()
        
        # Mock the export method to write to the BytesIO buffer
        def mock_export(buffer, format=None):
            # Write the encoded audio to the buffer
            buffer.write(b"encoded_audio")
            return buffer
        
        mock_audio_segment_instance.export.side_effect = mock_export

        with patch(
            "birdnetpi.services.audio_websocket_service.AudioSegment.__new__",
            return_value=mock_audio_segment_instance,
        ):
            # Use a numpy array to create valid int16 audio bytes
            raw_audio_np = np.zeros(48000, dtype=np.int16)  # 1 second of silence
            audio_data_bytes = raw_audio_np.tobytes()

            await audio_websocket_service.stream_audio_chunk(audio_data_bytes)

        assert "Error sending audio to WebSocket: Send error. Disconnecting." in caplog.text
        assert mock_websocket not in audio_websocket_service.connected_websockets

    @pytest.mark.asyncio
    async def test_stream_audio_chunk_error_encoding_audio(self, audio_websocket_service, caplog):
        """Should log error if audio encoding fails."""
        mock_websocket = AsyncMock(spec=WebSocket)
        audio_websocket_service.connected_websockets.add(mock_websocket)

        mock_audio_segment_instance = MagicMock()
        mock_audio_segment_instance.export.side_effect = Exception("Encoding error")

        with patch(
            "birdnetpi.services.audio_websocket_service.AudioSegment.__new__",
            return_value=mock_audio_segment_instance,
        ):
            # Explicitly set log level for this test
            caplog.set_level(logging.ERROR, logger="birdnetpi.services.audio_websocket_service")

            # Use a numpy array to create valid int16 audio bytes
            raw_audio_np = np.zeros(48000, dtype=np.int16)  # 1 second of silence
            audio_data_bytes = raw_audio_np.tobytes()

            await audio_websocket_service.stream_audio_chunk(audio_data_bytes)

        assert "Error encoding or streaming audio chunk: Encoding error" in caplog.text
        mock_websocket.send_bytes.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_streaming_loop(self, audio_websocket_service, caplog):
        """Should log message and enter infinite loop (mocked)."""
        with patch(
            "asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)
        ) as mock_sleep:
            with caplog.at_level(logging.INFO):
                try:
                    await audio_websocket_service.start_streaming_loop()
                except asyncio.CancelledError:  # Expected to break the loop
                    pass

            assert "AudioWebSocketService streaming loop started (passive)..." in caplog.text
            mock_sleep.assert_called_once_with(1)
