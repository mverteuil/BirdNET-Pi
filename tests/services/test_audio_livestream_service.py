import logging
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.services.audio_livestream_service import AudioLivestreamService


@pytest.fixture
def audio_livestream_service():
    """Return an AudioLivestreamService instance for testing."""
    return AudioLivestreamService("icecast://test_url", 48000, 1)


@pytest.fixture(autouse=True)
def caplog_for_audio_livestream_service(caplog):
    """Fixture to capture logs from audio_livestream_service.py."""
    caplog.set_level(logging.DEBUG, logger="birdnetpi.services.audio_livestream_service")
    yield


class TestAudioLivestreamService:
    """Test the AudioLivestreamService class."""

    def test_init(self, audio_livestream_service):
        """Should initialize with correct attributes."""
        assert audio_livestream_service.icecast_url == "icecast://test_url"
        assert audio_livestream_service.samplerate == 48000
        assert audio_livestream_service.channels == 1
        assert audio_livestream_service._ffmpeg_process is None

    @patch("subprocess.Popen")
    @patch("threading.Thread")
    def test_start_livestream(self, mock_thread, mock_popen, audio_livestream_service):
        """Should start the FFmpeg process and monitoring threads."""
        mock_ffmpeg_process = MagicMock()
        mock_popen.return_value = mock_ffmpeg_process

        audio_livestream_service.start_livestream()

        mock_popen.assert_called_once()
        assert audio_livestream_service._ffmpeg_process == mock_ffmpeg_process
        assert mock_thread.call_count == 2
        mock_thread.return_value.start.assert_called()

    def test_read_ffmpeg_output(self, audio_livestream_service, caplog):
        """Should log FFmpeg output."""
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = [b"line1\n", b"line2\n", b""]

        with caplog.at_level(logging.DEBUG):
            audio_livestream_service._read_ffmpeg_output(mock_pipe, "FFmpeg Test")
            assert "FFmpeg Test: line1" in caplog.text
            assert "FFmpeg Test: line2" in caplog.text

    def test_stream_audio_chunk_success(self, audio_livestream_service):
        """Should write audio data to FFmpeg stdin."""
        mock_stdin = MagicMock()
        audio_livestream_service._ffmpeg_process = MagicMock(stdin=mock_stdin)

        audio_data = b"test_audio_data"
        audio_livestream_service.stream_audio_chunk(audio_data)

        mock_stdin.write.assert_called_once_with(audio_data)

    def test_stream_audio_chunk_no_ffmpeg_process(self, audio_livestream_service, caplog):
        """Should log a warning if FFmpeg process is not running."""
        audio_livestream_service._ffmpeg_process = None

        with caplog.at_level(logging.WARNING):
            audio_livestream_service.stream_audio_chunk(b"test_audio_data")
            assert "FFmpeg process not running or stdin not available." in caplog.text

    @patch("birdnetpi.services.audio_livestream_service.AudioLivestreamService.stop_livestream")
    def test_stream_audio_chunk_broken_pipe_error(
        self, mock_stop_livestream, audio_livestream_service, caplog
    ):
        """Should handle BrokenPipeError and stop livestream."""
        mock_stdin = MagicMock()
        mock_stdin.write.side_effect = BrokenPipeError
        audio_livestream_service._ffmpeg_process = MagicMock(stdin=mock_stdin)

        with caplog.at_level(logging.ERROR):
            audio_livestream_service.stream_audio_chunk(b"test_audio_data")
            assert "Broken pipe: FFmpeg process might have terminated." in caplog.text
            mock_stop_livestream.assert_called_once()

    def test_stream_audio_chunk_generic_exception(self, audio_livestream_service, caplog):
        """Should log an error for generic exceptions during writing."""
        mock_stdin = MagicMock()
        mock_stdin.write.side_effect = Exception("Write error")
        audio_livestream_service._ffmpeg_process = MagicMock(stdin=mock_stdin)

        with caplog.at_level(logging.ERROR):
            audio_livestream_service.stream_audio_chunk(b"test_audio_data")
            assert "Error writing to FFmpeg stdin: Write error" in caplog.text

    def test_stop_livestream_process_running(self, audio_livestream_service, caplog):
        """Should terminate and wait for FFmpeg process."""
        mock_ffmpeg_process = MagicMock()
        audio_livestream_service._ffmpeg_process = mock_ffmpeg_process

        audio_livestream_service.stop_livestream()

        mock_ffmpeg_process.terminate.assert_called_once()
        mock_ffmpeg_process.wait.assert_called_once()
        assert audio_livestream_service._ffmpeg_process is None
        assert "FFmpeg process terminated." in caplog.text

    def test_stop_livestream_no_process_running(self, audio_livestream_service, caplog):
        """Should do nothing if no FFmpeg process is running."""
        audio_livestream_service._ffmpeg_process = None

        audio_livestream_service.stop_livestream()

        assert audio_livestream_service._ffmpeg_process is None
        assert "FFmpeg process terminated." not in caplog.text
