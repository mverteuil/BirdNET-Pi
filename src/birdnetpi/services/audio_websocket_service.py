import asyncio
import logging

from fastapi import WebSocket
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class AudioWebSocketService:
    """Manages real-time audio streaming over WebSockets."""

    def __init__(self, samplerate: int, channels: int) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.connected_websockets = set()
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

    async def stream_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Encode and stream a chunk of audio data to all connected WebSockets."""
        if not self.connected_websockets:
            return  # No clients to stream to

        try:
            # Create an AudioSegment from raw bytes
            audio_segment = AudioSegment(
                audio_data_bytes,
                sample_width=2,  # 2 bytes for int16
                frame_rate=self.samplerate,
                channels=self.channels,
            )

            # Export to a suitable streaming format (e.g., Opus or MP3)
            # Using a temporary in-memory file for efficiency
            # For real-time, consider a format that supports appending or direct byte streaming
            # For simplicity, let's use MP3 for now. Opus is better for real-time.
            encoded_audio_bytes = audio_segment.export(format="mp3").read()

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
