"""Tests for database models."""

from birdnetpi.detections.models import Detection


class TestDetection:
    """Test the Detection model class."""

    def test_get_display_name_returns_common_name(self):
        """Should get_display_name returns common name when available."""
        detection = Detection(
            species_tensor="Turdus migratorius_American Robin",
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.95,
        )

        result = detection.get_display_name()

        assert result == "American Robin"

    def test_get_display_name_falls_back_to_scientific_name(self):
        """Should get_display_name returns scientific name when common name is None."""
        detection = Detection(
            species_tensor="Turdus migratorius_American Robin",
            common_name=None,
            scientific_name="Turdus migratorius",
            confidence=0.95,
        )

        result = detection.get_display_name()

        assert result == "Turdus migratorius"
