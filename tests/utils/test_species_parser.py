"""Tests for species name parsing utilities."""

import pytest

from birdnetpi.utils.species_parser import (
    SpeciesComponents,
    SpeciesDisplayOptions,
    SpeciesParser,
    create_display_options_from_config,
)


class TestSpeciesParser:
    """Test cases for SpeciesParser functionality."""

    def test_parse_tensor_species_valid_format(self):
        """Test parsing valid tensor output format."""
        tensor_output = "Abeillia abeillei_Emerald-chinned Hummingbird"

        components = SpeciesParser.parse_tensor_species(tensor_output)

        assert components.scientific_name == "Abeillia abeillei"
        assert components.common_name == "Emerald-chinned Hummingbird"
        assert (
            components.common_name == "Emerald-chinned Hummingbird"
        )  # Placeholder until IOC service
        assert components.full_species == "Emerald-chinned Hummingbird (Abeillia abeillei)"

    def test_parse_tensor_species_another_example(self):
        """Test parsing another valid tensor output format."""
        tensor_output = "Turdus migratorius_American Robin"

        components = SpeciesParser.parse_tensor_species(tensor_output)

        assert components.scientific_name == "Turdus migratorius"
        assert components.common_name == "American Robin"
        assert components.common_name == "American Robin"
        assert components.full_species == "American Robin (Turdus migratorius)"

    def test_parse_tensor_species__invalid_format__no_underscore(self):
        """Test parsing fails with invalid format (no underscore)."""
        tensor_output = "Abeillia abeillei Emerald-chinned Hummingbird"

        with pytest.raises(ValueError, match="Invalid tensor species format"):
            SpeciesParser.parse_tensor_species(tensor_output)

    def test_parse_tensor_species__invalid_format__empty_parts(self):
        """Test parsing fails with empty components."""
        tensor_output = "_Emerald-chinned Hummingbird"

        with pytest.raises(ValueError, match="Invalid species components"):
            SpeciesParser.parse_tensor_species(tensor_output)

    def test_parse_tensor_species__invalid_format__empty_string(self):
        """Test parsing fails with empty string."""
        with pytest.raises(ValueError, match="Invalid tensor output"):
            SpeciesParser.parse_tensor_species("")

    def test_extract_common_name_prefer_ioc(self):
        """Test extracting common name preferring IOC."""
        tensor_output = "Turdus migratorius_American Robin"

        common_name = SpeciesParser.extract_common_name(tensor_output, prefer_ioc=True)

        assert common_name == "American Robin"  # IOC placeholder

    def test_extract_common_name_prefer_tensor(self):
        """Test extracting common name preferring tensor."""
        tensor_output = "Turdus migratorius_American Robin"

        common_name = SpeciesParser.extract_common_name(tensor_output, prefer_ioc=False)

        assert common_name == "American Robin"  # Tensor original

    def test_extract_scientific_name(self):
        """Test extracting scientific name."""
        tensor_output = "Turdus migratorius_American Robin"

        scientific_name = SpeciesParser.extract_scientific_name(tensor_output)

        assert scientific_name == "Turdus migratorius"

    def test_format_full_species(self):
        """Test formatting full species name."""
        tensor_output = "Turdus migratorius_American Robin"

        full_species = SpeciesParser.format_full_species(tensor_output)

        assert full_species == "American Robin (Turdus migratorius)"

    def test_is_valid_tensor_format_valid(self):
        """Test validation of valid tensor format."""
        tensor_output = "Turdus migratorius_American Robin"

        assert SpeciesParser.is_valid_tensor_format(tensor_output) is True

    def test_is_valid_tensor_format_invalid(self):
        """Test validation of invalid tensor format."""
        tensor_output = "Invalid format without underscore"

        assert SpeciesParser.is_valid_tensor_format(tensor_output) is False


class TestSpeciesDisplayOptions:
    """Test cases for species display formatting."""

    def test_format_species_for_display_full(self):
        """Test formatting species for full display."""
        components = SpeciesComponents(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            full_species="American Robin (Turdus migratorius)",
        )

        display_options = SpeciesDisplayOptions(show_scientific_name=True, show_common_name=True)

        result = SpeciesParser.format_species_for_display(components, display_options)

        assert result == "American Robin (Turdus migratorius)"

    def test_format_species_for_display_common_only(self):
        """Test formatting species for common name only."""
        components = SpeciesComponents(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            full_species="American Robin (Turdus migratorius)",
        )

        display_options = SpeciesDisplayOptions(show_scientific_name=False, show_common_name=True)

        result = SpeciesParser.format_species_for_display(components, display_options)

        assert result == "American Robin"

    def test_format_species_for_display_scientific_only(self):
        """Test formatting species for scientific name only."""
        components = SpeciesComponents(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            full_species="American Robin (Turdus migratorius)",
        )

        display_options = SpeciesDisplayOptions(show_scientific_name=True, show_common_name=False)

        result = SpeciesParser.format_species_for_display(components, display_options)

        assert result == "Turdus migratorius"


class TestConfigIntegration:
    """Test integration with configuration system."""

    def test_create_display_options_from_config_full(self):
        """Test creating display options from config for full display."""
        from unittest.mock import Mock

        config = Mock()
        config.species_display_mode = "full"
        config.language = "en"

        options = create_display_options_from_config(config)

        assert options.show_scientific_name is True
        assert options.show_common_name is True
        assert options.language_code == "en"

    def test_create_display_options_from_config_common_only(self):
        """Test creating display options from config for common name only."""
        from unittest.mock import Mock

        config = Mock()
        config.species_display_mode = "common_name"
        config.language = "es"

        options = create_display_options_from_config(config)

        assert options.show_scientific_name is False
        assert options.show_common_name is True
        assert options.language_code == "es"

    def test_create_display_options_from_config_scientific_only(self):
        """Test creating display options from config for scientific name only."""
        from unittest.mock import Mock

        config = Mock()
        config.species_display_mode = "scientific_name"
        config.language = "fr"

        options = create_display_options_from_config(config)

        assert options.show_scientific_name is True
        assert options.show_common_name is False
        assert options.language_code == "fr"

    def test_create_display_options_from_config_defaults(self):
        """Test creating display options from config with missing attributes."""
        from unittest.mock import Mock

        config = Mock()
        # Set attributes to what the function expects as defaults
        config.species_display_mode = "full"
        config.language = "en"

        options = create_display_options_from_config(config)

        assert options.show_scientific_name is True
        assert options.show_common_name is True
        assert options.language_code == "en"


class TestSpeciesParserWithIOC:
    """Test SpeciesParser functionality with IOC service."""

    def test_species_parser_initialization__ioc_service(self):
        """Test SpeciesParser initialization with IOC service."""
        # Create a temporary database service for testing
        import tempfile

        from birdnetpi.services.ioc_database_service import IOCDatabaseService

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_file:
            ioc_service = IOCDatabaseService(tmp_file.name)
            parser = SpeciesParser(ioc_service)

            assert parser.ioc_database is ioc_service

    def test_format_species_display_fallback_to_common_name(self):
        """Test format_species_for_display fallback when both display options are disabled."""
        components = SpeciesComponents(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            full_species="American Robin (Turdus migratorius)",
        )

        # Both show_scientific_name and show_common_name are False
        display_options = SpeciesDisplayOptions(show_scientific_name=False, show_common_name=False)

        result = SpeciesParser.format_species_for_display(components, display_options)

        # Should fallback to common_name (line 117)
        assert result == "American Robin"

    def test_format_species_display_non_english_language_fallback(self):
        """Test format_species_for_display with non-English language code fallback."""
        components = SpeciesComponents(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            full_species="American Robin (Turdus migratorius)",
        )

        # Non-English language with fallback enabled
        display_options = SpeciesDisplayOptions(
            show_scientific_name=True,
            show_common_name=True,
            language_code="es",  # Spanish
            fallback_to_common=True,
        )

        result = SpeciesParser.format_species_for_display(components, display_options)

        # Should use IOC English as fallback (line 125)
        assert result == "American Robin (Turdus migratorius)"


# TestMockIOCReferenceService class removed - obsolete after refactoring to IOCDatabaseService
