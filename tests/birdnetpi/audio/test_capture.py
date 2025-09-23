"""Tests for the AudioCaptureService class."""

import os
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from birdnetpi.audio.capture import AudioCaptureService
from birdnetpi.audio.filters import FilterChain


@pytest.fixture
def audio_service(test_config):
    """Create an AudioCaptureService instance."""
    return AudioCaptureService(test_config, analysis_fifo_fd=-1, livestream_fifo_fd=-1)


@pytest.fixture
def mock_device():
    """Create a mock audio device."""
    device = MagicMock()
    device.index = 1
    device.default_samplerate = 44100.0
    device.name = "Test Device"
    return device


# Basic AudioCaptureService tests


@patch("sounddevice.InputStream")
def test_start_capture_initializes_stream(mock_input_stream, audio_service):
    """Should initialize the sounddevice stream correctly."""
    # No device discovery needed - we always use the target sample rate
    audio_service.start_capture()

    # Should use BirdNET's required sample rate (48000) regardless of device native rate
    mock_input_stream.assert_called_once_with(
        device=audio_service.config.audio_device_index,
        samplerate=48000,  # BirdNET's required rate
        channels=audio_service.config.audio_channels,
        callback=audio_service._callback,
    )
    mock_input_stream.return_value.start.assert_called_once()


@patch("sounddevice.InputStream")
def test_stop_capture_stops_closes_stream(mock_input_stream, audio_service):
    """Should stop and close the sounddevice stream."""
    mock_input_stream.return_value.stopped = False  # Ensure it's not stopped initially
    audio_service.start_capture()
    audio_service.stop_capture()
    # Now using abort() for immediate stop instead of stop()
    mock_input_stream.return_value.abort.assert_called_once()
    mock_input_stream.return_value.close.assert_called_once()


@patch("sounddevice.InputStream", side_effect=Exception("Test Error"))
def test_start_capture_handles_exceptions(mock_input_stream, audio_service):
    """Should handle exceptions during stream initialization."""
    with pytest.raises(Exception) as exc_info:
        audio_service.start_capture()
    assert str(exc_info.value) == "Test Error"


# Callback function tests


@pytest.fixture
def audio_service_with_fds(test_config):
    """Create an AudioCaptureService with real file descriptors."""
    # Create real file descriptors for testing
    analysis_fd = os.open("/dev/null", os.O_WRONLY)
    livestream_fd = os.open("/dev/null", os.O_WRONLY)

    service = AudioCaptureService(
        test_config,
        analysis_fifo_fd=analysis_fd,
        livestream_fifo_fd=livestream_fd,
    )

    yield service

    # Cleanup
    try:
        os.close(analysis_fd)
    except OSError:
        pass
    try:
        os.close(livestream_fd)
    except OSError:
        pass


@patch("os.write")
def test_callback_processes_audio_data(mock_write, audio_service_with_fds):
    """Should process audio data and write to FIFOs."""
    # Create test audio data
    frames = 1024
    indata = np.random.rand(frames, 1).astype(np.float32)

    # Call the callback
    audio_service_with_fds._callback(indata, frames, None, None)

    # Verify data was written to both FIFOs
    assert mock_write.call_count == 2
    # Check that int16 conversion happened
    call_args_list = mock_write.call_args_list
    for call_args in call_args_list:
        _, audio_bytes = call_args[0]
        # Should be int16 bytes (2 bytes per sample)
        assert len(audio_bytes) == frames * 2


@patch("os.write")
@patch("birdnetpi.audio.capture.logger")
def test_callback_handles_stream_status_warning(mock_logger, mock_write, audio_service_with_fds):
    """Should log warning when stream status is not None."""
    frames = 512
    indata = np.zeros((frames, 1), dtype=np.float32)
    # Create a mock status object that simulates sounddevice CallbackFlags
    status = MagicMock()
    status.__str__ = Mock(return_value="input_overflow")
    status.__bool__ = Mock(return_value=True)

    audio_service_with_fds._callback(indata, frames, None, status)

    # Should log the status warning
    mock_logger.warning.assert_any_call("Audio stream status: %s", status)


@patch("os.write")
def test_callback_with_analysis_filter_chain(mock_write, audio_service_with_fds):
    """Should apply analysis filter chain to audio data."""
    # Create a mock filter chain
    mock_filter_chain = MagicMock()
    mock_filtered_audio = np.zeros(1024, dtype=np.int16)
    mock_filter_chain.process.return_value = mock_filtered_audio

    audio_service_with_fds.analysis_filter_chain = mock_filter_chain

    # Process audio
    frames = 1024
    indata = np.random.rand(frames, 1).astype(np.float32)
    audio_service_with_fds._callback(indata, frames, None, None)

    # Verify filter chain was called
    mock_filter_chain.process.assert_called_once()
    # Verify filtered audio was written
    mock_write.assert_any_call(
        audio_service_with_fds.analysis_fifo_fd, mock_filtered_audio.tobytes()
    )


@patch("os.write")
def test_callback_with_livestream_filter_chain(mock_write, audio_service_with_fds):
    """Should apply livestream filter chain to audio data."""
    # Create a mock filter chain
    mock_filter_chain = MagicMock()
    mock_filtered_audio = np.zeros(512, dtype=np.int16)
    mock_filter_chain.process.return_value = mock_filtered_audio

    audio_service_with_fds.livestream_filter_chain = mock_filter_chain

    # Process audio
    frames = 1024
    indata = np.random.rand(frames, 1).astype(np.float32)
    audio_service_with_fds._callback(indata, frames, None, None)

    # Verify filter chain was called
    mock_filter_chain.process.assert_called_once()
    # Verify filtered audio was written
    mock_write.assert_any_call(
        audio_service_with_fds.livestream_fifo_fd, mock_filtered_audio.tobytes()
    )


@patch("os.write", side_effect=BlockingIOError())
@patch("birdnetpi.audio.capture.logger")
def test_callback_handles_blocking_io_error(mock_logger, mock_write, audio_service_with_fds):
    """Should handle BlockingIOError gracefully."""
    frames = 256
    indata = np.zeros((frames, 1), dtype=np.float32)

    audio_service_with_fds._callback(indata, frames, None, None)

    # Should log warning about blocking
    mock_logger.warning.assert_called_with("FIFO write would block, skipping frame.")
    # Should not set shutdown flag
    assert not audio_service_with_fds._shutdown_requested


@patch("os.write", side_effect=BrokenPipeError())
@patch("birdnetpi.audio.capture.logger")
def test_callback_handles_broken_pipe_error(mock_logger, mock_write, audio_service_with_fds):
    """Should handle BrokenPipeError and request shutdown."""
    frames = 256
    indata = np.zeros((frames, 1), dtype=np.float32)

    audio_service_with_fds._callback(indata, frames, None, None)

    # Should log debug message
    mock_logger.debug.assert_called_with("FIFO closed, requesting shutdown.")
    # Should set shutdown flag
    assert audio_service_with_fds._shutdown_requested


@patch("os.write", side_effect=OSError(9, "Bad file descriptor"))
@patch("birdnetpi.audio.capture.logger")
def test_callback_handles_bad_file_descriptor(mock_logger, mock_write, audio_service_with_fds):
    """Should handle EBADF error during shutdown."""
    frames = 256
    indata = np.zeros((frames, 1), dtype=np.float32)

    audio_service_with_fds._callback(indata, frames, None, None)

    # Should log debug message
    mock_logger.debug.assert_called_with("FIFO file descriptor closed during shutdown.")
    # Should set shutdown flag
    assert audio_service_with_fds._shutdown_requested


@patch("os.write", side_effect=OSError(13, "Permission denied"))
@patch("birdnetpi.audio.capture.logger")
def test_callback_handles_other_os_errors(mock_logger, mock_write, audio_service_with_fds):
    """Should handle other OS errors."""
    frames = 256
    indata = np.zeros((frames, 1), dtype=np.float32)

    audio_service_with_fds._callback(indata, frames, None, None)

    # Should log error message
    mock_logger.error.assert_called()
    # Should not set shutdown flag for other errors
    assert not audio_service_with_fds._shutdown_requested


# Default device handling tests


@pytest.fixture
def audio_service_default_device(test_config):
    """Create an AudioCaptureService configured for default device."""
    test_config.audio_device_index = -1  # Use default device
    return AudioCaptureService(test_config, analysis_fifo_fd=-1, livestream_fifo_fd=-1)


@patch("sounddevice.InputStream")
def test_start_capture_with_default_device(mock_input_stream, audio_service_default_device):
    """Should use default device when device_index is -1."""
    audio_service_default_device.start_capture()

    # Should use BirdNET's required sample rate
    mock_input_stream.assert_called_once_with(
        device=-1,
        samplerate=48000,
        channels=audio_service_default_device.config.audio_channels,
        callback=audio_service_default_device._callback,
    )
    mock_input_stream.return_value.start.assert_called_once()


@patch("sounddevice.InputStream")
@patch("birdnetpi.audio.capture.logger")
def test_default_device_logging(mock_logger, mock_input_stream, audio_service_default_device):
    """Should log default device information."""
    audio_service_default_device.start_capture()

    # Should log audio capture stream started
    mock_logger.info.assert_any_call("Audio capture stream started at %dHz.", 48000)


# Filter chain configuration tests


@pytest.fixture
def audio_service_with_filters(test_config):
    """Create an AudioCaptureService with filter chains."""
    # Create mock filter chains
    mock_analysis_chain = MagicMock(spec=FilterChain)
    mock_analysis_chain.filters = []
    mock_analysis_chain.__len__ = Mock(return_value=1)

    mock_livestream_chain = MagicMock(spec=FilterChain)
    mock_livestream_chain.__len__ = Mock(return_value=2)

    return AudioCaptureService(
        test_config,
        analysis_fifo_fd=-1,
        livestream_fifo_fd=-1,
        analysis_filter_chain=mock_analysis_chain,
        livestream_filter_chain=mock_livestream_chain,
    )


@patch("sounddevice.InputStream")
@patch("birdnetpi.audio.capture.logger")
def test_filter_chain_with_resampling(mock_logger, mock_input_stream, audio_service_with_filters):
    """Should use sounddevice automatic resampling, not manual filter."""
    audio_service_with_filters.start_capture()

    # Should NOT add manual resampling filter (sounddevice handles it)
    assert len(audio_service_with_filters.analysis_filter_chain.filters) == 0

    # Should configure chains with target sample rate
    audio_service_with_filters.analysis_filter_chain.configure.assert_called_once_with(48000, 1)
    audio_service_with_filters.livestream_filter_chain.configure.assert_called_once_with(48000, 1)

    # Should log automatic resampling info
    mock_logger.info.assert_any_call(
        "Using sounddevice automatic resampling (PortAudio) - requesting %dHz", 48000
    )


@patch("sounddevice.InputStream")
def test_filter_chain_without_resampling(mock_input_stream, audio_service_with_filters):
    """Should not add resampling filter regardless of rates."""
    audio_service_with_filters.start_capture()

    # Should not add resampling filter (sounddevice handles any needed conversion)
    assert len(audio_service_with_filters.analysis_filter_chain.filters) == 0

    # Should configure chains with target rate
    audio_service_with_filters.analysis_filter_chain.configure.assert_called_once_with(48000, 1)
    audio_service_with_filters.livestream_filter_chain.configure.assert_called_once_with(48000, 1)


@patch("sounddevice.InputStream")
@patch("birdnetpi.audio.capture.logger")
def test_livestream_filter_chain_configuration(
    mock_logger, mock_input_stream, audio_service_with_filters
):
    """Should configure livestream filter chain with target rate."""
    audio_service_with_filters.start_capture()

    # Livestream should use target rate (sounddevice handles resampling)
    audio_service_with_filters.livestream_filter_chain.configure.assert_called_once_with(48000, 1)

    # Should log configuration
    mock_logger.info.assert_any_call("Livestream filter chain configured with %d filters", 2)


# Stop capture edge cases tests


@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_when_stream_already_stopped(mock_logger, audio_service):
    """Should handle stopping an already stopped stream."""
    # Create a mock stream that's already stopped
    mock_stream = MagicMock()
    mock_stream.stopped = True
    audio_service.stream = mock_stream

    audio_service.stop_capture()

    # Should not try to abort or close
    mock_stream.abort.assert_not_called()
    mock_stream.close.assert_not_called()

    # Should log that stream is not running
    mock_logger.info.assert_called_with("Audio capture stream is not running.")


@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_when_no_stream(mock_logger, audio_service):
    """Should handle stopping when no stream exists."""
    audio_service.stream = None

    audio_service.stop_capture()

    # Should log that stream is not running
    mock_logger.info.assert_called_with("Audio capture stream is not running.")


@patch("time.sleep")
@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_handles_pthread_join_error(mock_logger, mock_sleep, audio_service):
    """Should handle pthread_join errors gracefully."""
    mock_stream = MagicMock()
    mock_stream.stopped = False
    mock_stream.close.side_effect = Exception("pthread_join failed")
    audio_service.stream = mock_stream

    audio_service.stop_capture()

    # Should log as debug (expected error)
    mock_logger.debug.assert_called()
    # Should not log as error
    mock_logger.error.assert_not_called()


@patch("time.sleep")
@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_handles_pa_unix_thread_error(mock_logger, mock_sleep, audio_service):
    """Should handle PaUnixThread_Terminate errors gracefully."""
    mock_stream = MagicMock()
    mock_stream.stopped = False
    mock_stream.close.side_effect = Exception("PaUnixThread_Terminate error")
    audio_service.stream = mock_stream

    audio_service.stop_capture()

    # Should log as debug (expected error)
    mock_logger.debug.assert_called()
    # Should not log as error
    mock_logger.error.assert_not_called()


@patch("time.sleep")
@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_handles_generic_exceptions(mock_logger, mock_sleep, audio_service):
    """Should log generic exceptions as errors."""
    mock_stream = MagicMock()
    mock_stream.stopped = False
    mock_stream.close.side_effect = Exception("Unexpected error")
    audio_service.stream = mock_stream

    audio_service.stop_capture()

    # Should log as error
    mock_logger.error.assert_called_with("Error stopping audio stream: Unexpected error")


@patch("time.sleep")
@patch("birdnetpi.audio.capture.logger")
def test_stop_capture_normal_flow(mock_logger, mock_sleep, audio_service):
    """Should properly stop and close stream in normal flow."""
    mock_stream = MagicMock()
    mock_stream.stopped = False
    audio_service.stream = mock_stream

    audio_service.stop_capture()

    # Should abort then close
    mock_stream.abort.assert_called_once()
    mock_stream.close.assert_called_once()
    # Should wait between abort and close
    mock_sleep.assert_called_once_with(0.1)
    # Should log success
    mock_logger.info.assert_called_with("Audio capture stream stopped and closed.")


# Integration tests


@patch("sounddevice.InputStream")
def test_full_audio_pipeline(mock_input_stream, test_config):
    """Should test complete flow from start to stop."""
    # Setup mocks
    mock_stream = MagicMock()
    mock_stream.stopped = False
    mock_input_stream.return_value = mock_stream

    # Create service with filter chains
    analysis_chain = FilterChain()
    livestream_chain = FilterChain()

    service = AudioCaptureService(
        test_config,
        analysis_fifo_fd=-1,
        livestream_fifo_fd=-1,
        analysis_filter_chain=analysis_chain,
        livestream_filter_chain=livestream_chain,
    )

    # Start capture
    service.start_capture()

    # Verify stream was created and started
    mock_input_stream.assert_called_once()
    mock_stream.start.assert_called_once()

    # Stop capture
    service.stop_capture()

    # Verify stream was stopped
    mock_stream.abort.assert_called_once()
    mock_stream.close.assert_called_once()


@patch("sounddevice.InputStream")
def test_multiple_start_stop_cycles(mock_input_stream, test_config):
    """Should test repeated start/stop operations."""
    mock_stream = MagicMock()
    mock_stream.stopped = False
    mock_input_stream.return_value = mock_stream

    service = AudioCaptureService(test_config, analysis_fifo_fd=-1, livestream_fifo_fd=-1)

    # First cycle
    service.start_capture()
    service.stop_capture()

    # Reset mock state but keep the call counts
    first_start_count = mock_stream.start.call_count
    first_abort_count = mock_stream.abort.call_count
    first_close_count = mock_stream.close.call_count

    mock_stream.stopped = False  # Reset stream state for second cycle
    service.stream = None  # Reset service's stream reference

    # Second cycle
    service.start_capture()
    service.stop_capture()

    # Should work without issues
    assert mock_stream.start.call_count == first_start_count + 1
    assert mock_stream.abort.call_count == first_abort_count + 1
    assert mock_stream.close.call_count == first_close_count + 1
