"""Tests for DetectionResponse model with first detection fields."""

from datetime import UTC, datetime
from uuid import uuid4

from birdnetpi.web.models.detections import DetectionResponse


class TestDetectionResponseFirstDetectionFields:
    """Test DetectionResponse model handles first detection fields correctly."""

    def test_detection_response_with_all_first_detection_fields(self):
        """Should serialize DetectionResponse with all first detection fields populated."""
        detection_id = uuid4()
        audio_file_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        first_ever = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)
        first_period = datetime(2024, 1, 15, 8, 30, 0, tzinfo=UTC)

        response = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
            date="2024-01-15",
            time="10:30:00",
            latitude=45.5,
            longitude=-73.6,
            family="Turdidae",
            genus="Turdus",
            order_name="Passeriformes",
            audio_file_id=audio_file_id,
            # First detection fields
            is_first_ever=True,
            is_first_in_period=True,
            first_ever_detection=first_ever,
            first_period_detection=first_period,
        )

        # Verify model instance
        assert response.id == detection_id
        assert response.is_first_ever is True
        assert response.is_first_in_period is True
        assert response.first_ever_detection == first_ever
        assert response.first_period_detection == first_period

        # Verify JSON serialization
        json_data = response.model_dump()
        assert json_data["is_first_ever"] is True
        assert json_data["is_first_in_period"] is True
        assert isinstance(json_data["first_ever_detection"], datetime)
        assert isinstance(json_data["first_period_detection"], datetime)

    def test_detection_response_with_no_first_detection_fields(self):
        """Should allow DetectionResponse without first detection fields (all None)."""
        detection_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        response = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
            # First detection fields explicitly None
            is_first_ever=None,
            is_first_in_period=None,
            first_ever_detection=None,
            first_period_detection=None,
        )

        # Verify model instance allows None
        assert response.is_first_ever is None
        assert response.is_first_in_period is None
        assert response.first_ever_detection is None
        assert response.first_period_detection is None

        # Verify JSON serialization includes None values
        json_data = response.model_dump()
        assert json_data["is_first_ever"] is None
        assert json_data["is_first_in_period"] is None
        assert json_data["first_ever_detection"] is None
        assert json_data["first_period_detection"] is None

    def test_detection_response_first_detection_fields_are_optional(self):
        """Should allow DetectionResponse without specifying first detection fields."""
        detection_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Create response without first detection fields
        response = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
        )

        # Verify fields default to None
        assert response.is_first_ever is None
        assert response.is_first_in_period is None
        assert response.first_ever_detection is None
        assert response.first_period_detection is None

    def test_detection_response_partial_first_detection_fields(self):
        """Should allow DetectionResponse with some first detection fields populated."""
        detection_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        first_ever = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)

        response = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
            # Only some first detection fields
            is_first_ever=True,
            first_ever_detection=first_ever,
            # These remain None
            is_first_in_period=None,
            first_period_detection=None,
        )

        # Verify mixed field values
        assert response.is_first_ever is True
        assert response.first_ever_detection == first_ever
        assert response.is_first_in_period is None
        assert response.first_period_detection is None

    def test_detection_response_json_round_trip(self):
        """Should serialize and deserialize DetectionResponse with first detection fields."""
        detection_id = uuid4()
        audio_file_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        first_ever = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)
        first_period = datetime(2024, 1, 15, 8, 30, 0, tzinfo=UTC)

        original = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
            audio_file_id=audio_file_id,
            is_first_ever=True,
            is_first_in_period=True,
            first_ever_detection=first_ever,
            first_period_detection=first_period,
        )

        # Serialize to JSON
        json_str = original.model_dump_json()

        # Deserialize from JSON
        reconstructed = DetectionResponse.model_validate_json(json_str)

        # Verify all fields match
        assert reconstructed.id == original.id
        assert reconstructed.is_first_ever == original.is_first_ever
        assert reconstructed.is_first_in_period == original.is_first_in_period
        assert reconstructed.first_ever_detection == original.first_ever_detection
        assert reconstructed.first_period_detection == original.first_period_detection

    def test_detection_response_false_flags(self):
        """Should properly handle False values for first detection flags."""
        detection_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        first_ever = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)
        first_period = datetime(2024, 1, 10, 9, 0, 0, tzinfo=UTC)

        response = DetectionResponse(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.92,
            timestamp=timestamp,
            # This detection is NOT the first (flags are False)
            is_first_ever=False,
            is_first_in_period=False,
            # But we still have the timestamps of when the first detections occurred
            first_ever_detection=first_ever,
            first_period_detection=first_period,
        )

        # Verify False is distinct from None
        assert response.is_first_ever is False
        assert response.is_first_in_period is False
        assert response.first_ever_detection is not None
        assert response.first_period_detection is not None

        # Verify JSON serialization preserves False
        json_data = response.model_dump()
        assert json_data["is_first_ever"] is False
        assert json_data["is_first_in_period"] is False
