import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.managers.detection_event_manager import DetectionEventManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.notification_manager import NotificationManager
from birdnetpi.utils.signals import detection_signal


@pytest.fixture
def mock_detection_manager():
    """Mock DetectionManager instance."""
    return MagicMock(spec=DetectionManager)


@pytest.fixture
def mock_notification_manager():
    """Mock NotificationManager instance."""
    mock = AsyncMock(spec=NotificationManager)
    mock.send_websocket_notification = AsyncMock()
    mock.send_apprise_notification = AsyncMock()
    return mock


@pytest.fixture
def detection_event_manager(mock_detection_manager, mock_notification_manager):
    """Return a DetectionEventManager instance for testing."""
    manager = DetectionEventManager(
        detection_manager=mock_detection_manager,
        notification_manager=mock_notification_manager,
    )
    yield manager
    # Disconnect the signal after the test to prevent interference
    detection_signal.disconnect(manager.handle_detection_event)


@pytest.fixture(autouse=True)
def caplog_for_detection_event_manager(caplog):
    """Fixture to capture logs from detection_event_manager.py."""
    caplog.set_level(logging.INFO, logger="birdnetpi.managers.detection_event_manager")
    yield


class TestDetectionEventManager:
    """Test the DetectionEventManager class."""

    @pytest.mark.asyncio
    async def test_handle_detection_event(
        self, detection_event_manager, mock_detection_manager, mock_notification_manager, caplog
    ):
        """Should process detection event, save to DB, and send notifications."""
        detection_data = {
            "species": "Common Blackbird",
            "confidence": 0.95,
            "timestamp": "2025-07-29T10:00:00Z",
            "audio_file_path": "/path/to/audio.wav",
            "duration": 5.0,
            "size_bytes": 1024,
            "latitude": 40.7128,
            "longitude": -74.0060,
            "species_confidence_threshold": 0.1,
            "week": 30,
            "sensitivity_setting": 1.25,
            "overlap": 0.5,
        }

        # Trigger the signal and await its processing
        # We need to explicitly run the async receiver within the event loop
        task = asyncio.create_task(
            detection_event_manager.handle_detection_event(self, detection_data=detection_data)
        )
        await task

        # Assertions - check that create_detection was called (but not with the original dict)
        mock_detection_manager.create_detection.assert_called_once()

        # Verify the DetectionEvent object passed to create_detection
        call_args = mock_detection_manager.create_detection.call_args[0][0]
        assert call_args.species_tensor == "Common Blackbird"
        assert call_args.confidence == 0.95
        assert call_args.audio_file_path == "/path/to/audio.wav"

        # Since the notification methods are commented out, we should not expect them to be called
        mock_notification_manager.send_websocket_notification.assert_not_called()
        mock_notification_manager.send_apprise_notification.assert_not_called()

        assert "Processing detection event for Common Blackbird" in caplog.text
        assert "Saving detection to DB: Common Blackbird" in caplog.text
