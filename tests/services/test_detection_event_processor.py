import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.detection_event_processor import DetectionEventProcessor
from birdnetpi.services.notification_service import NotificationService
from birdnetpi.utils.signals import detection_signal


@pytest.fixture
def mock_detection_manager():
    """Mock DetectionManager instance."""
    return MagicMock(spec=DetectionManager)


@pytest.fixture
def mock_notification_service():
    """Mock NotificationService instance."""
    mock = AsyncMock(spec=NotificationService)
    mock.send_websocket_notification = AsyncMock()
    mock.send_apprise_notification = AsyncMock()
    return mock


@pytest.fixture
def detection_event_processor(mock_detection_manager, mock_notification_service):
    """Return a DetectionEventProcessor instance for testing."""
    processor = DetectionEventProcessor(
        detection_manager=mock_detection_manager,
        notification_service=mock_notification_service,
    )
    yield processor
    # Disconnect the signal after the test to prevent interference
    detection_signal.disconnect(processor.handle_detection_event)


@pytest.fixture(autouse=True)
def caplog_for_detection_event_processor(caplog):
    """Fixture to capture logs from detection_event_processor.py."""
    caplog.set_level(logging.INFO, logger="birdnetpi.services.detection_event_processor")
    yield


class TestDetectionEventProcessor:
    """Test the DetectionEventProcessor class."""

    @pytest.mark.asyncio
    async def test_handle_detection_event(
        self, detection_event_processor, mock_detection_manager, mock_notification_service, caplog
    ):
        """Should process detection event, save to DB, and send notifications."""
        detection_data = {
            "species": "Common Blackbird",
            "confidence": 0.95,
            "timestamp": "2025-07-29T10:00:00Z",
            "audio_file_path": "/path/to/audio.wav",
            "duration": 5.0,
            "size_bytes": 1024,
        }

        # Trigger the signal and await its processing
        # We need to explicitly run the async receiver within the event loop
        task = asyncio.create_task(
            detection_event_processor.handle_detection_event(self, detection_data=detection_data)
        )
        await task

        # Assertions
        mock_detection_manager.create_detection.assert_called_once_with(detection_data)
        mock_notification_service.send_websocket_notification.assert_called_once_with(
            {
                "type": "detection",
                "species": "Common Blackbird",
                "confidence": 0.95,
                "timestamp": "2025-07-29T10:00:00Z",
            }
        )
        mock_notification_service.send_apprise_notification.assert_called_once_with(
            title="New Bird Detection: Common Blackbird",
            body="Confidence: 0.95 at 2025-07-29T10:00:00Z",
        )
        assert "Processing detection event for Common Blackbird" in caplog.text
        assert "Simulating saving detection to DB: Common Blackbird" in caplog.text
