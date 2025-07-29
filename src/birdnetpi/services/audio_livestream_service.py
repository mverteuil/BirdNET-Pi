import logging
import subprocess
import threading
from typing import BinaryIO

logger = logging.getLogger(__name__)


class AudioLivestreamService:
    """Service for handling audio livestreaming."""

    def __init__(self, icecast_url: str, samplerate: int, channels: int) -> None:
        self.icecast_url = icecast_url
        self.samplerate = samplerate
        self.channels = channels
        self._ffmpeg_process = None
        logger.info("AudioLivestreamService initialized.")

    def start_livestream(self) -> None:
        """Start the FFmpeg process for livestreaming."""
        ffmpeg_command = [
            "ffmpeg",
            "-v",
            "debug",  # Add verbose logging
            "-f",
            "s16le",  # Input format: signed 16-bit little-endian
            "-ar",
            str(self.samplerate),
            "-ac",
            str(self.channels),
            "-i",
            "-",  # Input from stdin (the FIFO)
            "-acodec",
            "libmp3lame",  # MP3 encoder
            "-b:a",
            "128k",  # Audio bitrate
            "-content_type",
            "audio/mpeg",
            "-f",
            "mp3",  # Output format
            self.icecast_url,
        ]

        self._ffmpeg_process = subprocess.Popen(
            ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        logger.info("FFmpeg process started for livestreaming.")

        # Start a thread to read FFmpeg's stderr and stdout
        self._stderr_thread = threading.Thread(
            target=self._read_ffmpeg_output, args=(self._ffmpeg_process.stderr, "FFmpeg STDERR")
        )
        self._stdout_thread = threading.Thread(
            target=self._read_ffmpeg_output, args=(self._ffmpeg_process.stdout, "FFmpeg STDOUT")
        )
        self._stderr_thread.daemon = True
        self._stdout_thread.daemon = True
        self._stderr_thread.start()
        self._stdout_thread.start()

    def _read_ffmpeg_output(self, pipe: BinaryIO, name: str) -> None:
        for line in iter(pipe.readline, b""):
            logger.debug("%s: %s", name, line.decode().strip())

    def stream_audio_chunk(self, audio_data_bytes: bytes) -> None:
        """Streams a chunk of audio data.

        Args:
            audio_data_bytes (bytes): Raw audio data in bytes (int16 format).
        """
        if self._ffmpeg_process and self._ffmpeg_process.stdin:
            try:
                self._ffmpeg_process.stdin.write(audio_data_bytes)
            except BrokenPipeError:
                logger.error("Broken pipe: FFmpeg process might have terminated.")
                self.stop_livestream()
            except Exception as e:
                logger.error("Error writing to FFmpeg stdin: %s", e)
        else:
            logger.warning("FFmpeg process not running or stdin not available.")

    def stop_livestream(self) -> None:
        """Stop the FFmpeg process."""
        if self._ffmpeg_process:
            logger.info("Terminating FFmpeg process...")
            self._ffmpeg_process.terminate()
            self._ffmpeg_process.wait()
            self._ffmpeg_process = None
            logger.info("FFmpeg process terminated.")
