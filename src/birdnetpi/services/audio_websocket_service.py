import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from fastapi import WebSocket
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class AudioWebSocketService:
    """Manages real-time audio streaming over WebSockets."""

    def __init__(self, samplerate: int, channels: int) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.connected_websockets = set()
        # Thread pool for CPU-intensive MP3 encoding
        self.thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio_encoder")
        logger.info("AudioWebSocketService initialized.")

    async def connect_websocket(self, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        self.connected_websockets.add(websocket)
        logger.info(
            "New WebSocket connected. Total connections: %s", len(self.connected_websockets)
        )

    async def disconnect_websocket(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        self.connected_websockets.remove(websocket)
        logger.info("WebSocket disconnected. Total connections: %s", len(self.connected_websockets))

    def _encode_audio_to_mp3(self, audio_data_bytes: bytes) -> bytes:
        """Encode audio data to MP3 format in a separate thread."""
        # Create an AudioSegment from raw bytes
        audio_segment = AudioSegment(
            audio_data_bytes,
            sample_width=2,  # 2 bytes for int16
            frame_rate=self.samplerate,
            channels=self.channels,
        )

        # Export to MP3 format
        buffer = BytesIO()
        audio_segment.export(buffer, format="mp3")
        return buffer.getvalue()

    async def stream_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Encode and stream a chunk of audio data to all connected WebSockets."""
        if not self.connected_websockets:
            return  # No clients to stream to

        try:
            # Encode audio to MP3 in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            encoded_audio_bytes = await loop.run_in_executor(
                self.thread_pool, self._encode_audio_to_mp3, audio_data_bytes
            )

            # Send to all connected WebSockets
            for websocket in list(
                self.connected_websockets
            ):  # Iterate over a copy to allow modification during loop
                try:
                    await websocket.send_bytes(encoded_audio_bytes)
                except Exception as e:
                    logger.error("Error sending audio to WebSocket: %s. Disconnecting.", e)
                    await self.disconnect_websocket(websocket)

        except Exception as e:
            logger.error("Error encoding or streaming audio chunk: %s", e, exc_info=True)

    async def start_streaming_loop(self) -> None:
        """Provide a continuous streaming loop if needed.

        Streaming is driven by stream_audio_chunk calls.
        """
        logger.info("AudioWebSocketService streaming loop started (passive)....")
        while True:
            await asyncio.sleep(1)  # Keep alive
