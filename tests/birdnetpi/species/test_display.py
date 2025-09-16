"""Tests for the SpeciesDisplayService module."""

from unittest.mock import MagicMock

import pytest

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
def config():
    """Create a mock config with default display settings."""
    mock_config = MagicMock(spec=BirdNETConfig)
    mock_config.species_display_mode = "full"  # Default to full mode
    return mock_config


@pytest.fixture
def display_service(config):
    """Create a SpeciesDisplayService instance with mock config."""
    return SpeciesDisplayService(config)


@pytest.fixture
def detection_with_all_names():
    """Create a mock detection with all name fields populated."""
    detection = MagicMock()
    detection.scientific_name = "Turdus migratorius"
    detection.common_name = "Robin"
    detection.ioc_english_name = "American Robin"
    detection.translated_name = "Rouge-gorge"
    return detection


@pytest.fixture
def detection_minimal():
    """Create a mock detection with minimal name fields."""
    detection = MagicMock()
    detection.scientific_name = "Corvus corax"
    detection.common_name = "Raven"
    detection.ioc_english_name = None
    detection.translated_name = None
    return detection


@pytest.fixture
def detection_no_common():
    """Create a mock detection with no common name."""
    detection = MagicMock()
    detection.scientific_name = "Passer domesticus"
    detection.common_name = None
    detection.ioc_english_name = "House Sparrow"
    detection.translated_name = "Moineau domestique"
    return detection


class TestFormatSpeciesDisplay:
    """Test the format_species_display method."""

    def test_scientific_name_mode(self, config, detection_with_all_names):
        """Should return scientific name when mode is scientific_name."""
        config.species_display_mode = "scientific_name"
        service = SpeciesDisplayService(config)

        result = service.format_species_display(detection_with_all_names)

        assert result == "Turdus migratorius"

    def test_prefer_translation_with_translation(self, display_service, detection_with_all_names):
        """Should prefer translated name when prefer_translation is True."""
        result = display_service.format_species_display(
            detection_with_all_names, prefer_translation=True
        )

        assert result == "Rouge-gorge"

    def test_prefer_translation_no_translation_falls_back_to_ioc(
        self, display_service, detection_no_common
    ):
        """Should fall back to IOC name when translation preferred but not available."""
        detection_no_common.translated_name = None

        result = display_service.format_species_display(
            detection_no_common, prefer_translation=True
        )

        assert result == "House Sparrow"

    def test_no_prefer_translation_uses_ioc_first(self, display_service, detection_with_all_names):
        """Should use IOC name first when prefer_translation is False."""
        result = display_service.format_species_display(
            detection_with_all_names, prefer_translation=False
        )

        assert result == "American Robin"

    def test_no_ioc_falls_back_to_translation(self, display_service):
        """Should fall back to translation when IOC not available."""
        detection = MagicMock()
        detection.scientific_name = "Test species"
        detection.common_name = "Common"
        detection.ioc_english_name = None
        detection.translated_name = "Translated"

        result = display_service.format_species_display(detection, prefer_translation=False)

        assert result == "Translated"

    def test_no_ioc_no_translation_uses_common(self, display_service, detection_minimal):
        """Should use common name when no IOC or translation available."""
        result = display_service.format_species_display(detection_minimal)

        assert result == "Raven"

    def test_fallback_to_scientific_when_no_common(self, display_service):
        """Should fall back to scientific name when no common name available."""
        detection = MagicMock()
        detection.scientific_name = "Fallback species"
        detection.common_name = None
        detection.ioc_english_name = None
        detection.translated_name = None

        result = display_service.format_species_display(detection)

        assert result == "Fallback species"


class TestFormatFullSpeciesDisplay:
    """Test the format_full_species_display method."""

    def test_scientific_name_mode(self, config, detection_with_all_names):
        """Should return only scientific name in scientific mode."""
        config.species_display_mode = "scientific_name"
        service = SpeciesDisplayService(config)

        result = service.format_full_species_display(detection_with_all_names)

        assert result == "Turdus migratorius"

    def test_common_name_mode(self, config, detection_with_all_names):
        """Should return only common name in common mode."""
        config.species_display_mode = "common_name"
        service = SpeciesDisplayService(config)

        result = service.format_full_species_display(detection_with_all_names)

        # Should use IOC name as it's available
        assert result == "American Robin"

    def test_full_mode(self, display_service, detection_with_all_names):
        """Should return 'Common (Scientific)' format in full mode."""
        result = display_service.format_full_species_display(detection_with_all_names)

        assert result == "American Robin (Turdus migratorius)"

    def test_full_mode_with_translation_preference(self, display_service, detection_with_all_names):
        """Should use translated name in full mode when preferred."""
        result = display_service.format_full_species_display(
            detection_with_all_names, prefer_translation=True
        )

        assert result == "Rouge-gorge (Turdus migratorius)"


class TestHelperMethods:
    """Test the helper methods of SpeciesDisplayService."""

    def test_get_display_mode(self, config):
        """Should return the current display mode from config."""
        config.species_display_mode = "scientific_name"
        service = SpeciesDisplayService(config)

        assert service.get_display_mode() == "scientific_name"

        config.species_display_mode = "common_name"
        assert service.get_display_mode() == "common_name"

        config.species_display_mode = "full"
        assert service.get_display_mode() == "full"

    def test_should_show_scientific_name(self, config):
        """Should return True for scientific_name and full modes."""
        service = SpeciesDisplayService(config)

        config.species_display_mode = "scientific_name"
        assert service.should_show_scientific_name() is True

        config.species_display_mode = "full"
        assert service.should_show_scientific_name() is True

        config.species_display_mode = "common_name"
        assert service.should_show_scientific_name() is False

    def test_should_show_common_name(self, config):
        """Should return True for common_name and full modes."""
        service = SpeciesDisplayService(config)

        config.species_display_mode = "common_name"
        assert service.should_show_common_name() is True

        config.species_display_mode = "full"
        assert service.should_show_common_name() is True

        config.species_display_mode = "scientific_name"
        assert service.should_show_common_name() is False


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_all_names_none_except_scientific(self, display_service):
        """Should handle detection with only scientific name."""
        detection = MagicMock()
        detection.scientific_name = "Only scientific"
        detection.common_name = None
        detection.ioc_english_name = None
        detection.translated_name = None

        result = display_service.format_species_display(detection)
        assert result == "Only scientific"

        full_result = display_service.format_full_species_display(detection)
        assert full_result == "Only scientific (Only scientific)"

    def test_empty_strings_treated_as_none(self, display_service):
        """Should treat empty strings as None for fallback logic."""
        detection = MagicMock()
        detection.scientific_name = "Scientific name"
        detection.common_name = ""
        detection.ioc_english_name = ""
        detection.translated_name = "Translation"

        # Empty strings should be falsy, so it should use translation
        result = display_service.format_species_display(detection, prefer_translation=False)
        assert result == "Translation"

    def test_prefer_translation_all_none_fallback(self, display_service):
        """Should handle prefer_translation=True with no translation or IOC available."""
        detection = MagicMock()
        detection.scientific_name = "Scientia fallbackus"
        detection.common_name = "Fallback Bird"
        detection.ioc_english_name = None
        detection.translated_name = None

        # With prefer_translation=True but no translation or IOC, should fall back to common
        result = display_service.format_species_display(detection, prefer_translation=True)
        assert result == "Fallback Bird"

    def test_type_checking_import(self):
        """Should handle TYPE_CHECKING import correctly."""
        # This tests that the TYPE_CHECKING guard works properly
        # The import should not fail even though we're not in type checking mode
        from birdnetpi.species.display import SpeciesDisplayService

        assert SpeciesDisplayService is not None
