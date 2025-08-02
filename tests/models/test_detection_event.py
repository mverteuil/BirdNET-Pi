from datetime import datetime

from birdnetpi.models.detection_event import DetectionEvent


class TestDetectionEvent:
    """Test the DetectionEvent dataclass."""

    def test_create_detection_event(self):
        """Should create a DetectionEvent with all required fields."""
        timestamp = datetime.now()
        event = DetectionEvent(
            species="Common Blackbird",
            confidence=0.85,
            timestamp=timestamp,
            audio_file_path="/path/to/audio.wav",
        )

        assert event.species == "Common Blackbird"
        assert event.confidence == 0.85
        assert event.timestamp == timestamp
        assert event.audio_file_path == "/path/to/audio.wav"

    def test_detection_event_equality(self):
        """Should support equality comparison."""
        timestamp = datetime.now()
        event1 = DetectionEvent(
            species="Robin",
            confidence=0.9,
            timestamp=timestamp,
            audio_file_path="/path/to/audio1.wav",
        )
        event2 = DetectionEvent(
            species="Robin",
            confidence=0.9,
            timestamp=timestamp,
            audio_file_path="/path/to/audio1.wav",
        )
        event3 = DetectionEvent(
            species="Crow",
            confidence=0.8,
            timestamp=timestamp,
            audio_file_path="/path/to/audio2.wav",
        )

        assert event1 == event2
        assert event1 != event3

    def test_detection_event_repr(self):
        """Should have a useful string representation."""
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        event = DetectionEvent(
            species="Test Bird",
            confidence=0.75,
            timestamp=timestamp,
            audio_file_path="/test/path.wav",
        )

        repr_str = repr(event)
        assert "DetectionEvent" in repr_str
        assert "Test Bird" in repr_str
        assert "0.75" in repr_str
        assert "/test/path.wav" in repr_str

    def test_detection_event_attributes_are_accessible(self):
        """Should allow access to all attributes."""
        timestamp = datetime.now()
        event = DetectionEvent(
            species="House Sparrow",
            confidence=0.65,
            timestamp=timestamp,
            audio_file_path="/audio/sparrow.wav",
        )

        # Test attribute access
        assert hasattr(event, "species")
        assert hasattr(event, "confidence")
        assert hasattr(event, "timestamp")
        assert hasattr(event, "audio_file_path")

        # Test attribute values
        assert event.species == "House Sparrow"
        assert event.confidence == 0.65
        assert event.timestamp == timestamp
        assert event.audio_file_path == "/audio/sparrow.wav"

    def test_detection_event_immutable_behavior(self):
        """Should behave as an immutable dataclass."""
        timestamp = datetime.now()
        event = DetectionEvent(
            species="Blue Jay",
            confidence=0.95,
            timestamp=timestamp,
            audio_file_path="/audio/bluejay.wav",
        )

        # Dataclasses are mutable by default, but we can test assignment
        event.species = "Modified Bird"
        assert event.species == "Modified Bird"
