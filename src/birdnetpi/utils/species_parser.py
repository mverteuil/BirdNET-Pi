"""Species name parsing utilities for BirdNET-Pi with IOC integration.

This module provides utilities to parse species names from tensor model output
and normalize them against IOC (International Ornithological Committee) World Bird Names
standards. The scientific name serves as the primary key, with IOC English common names
as the canonical reference and internationalization layered on top.

Architecture:
- Scientific name: Immutable identifier and primary key
- IOC English: Canonical common name reference (fallback to American English)
- Tensor parsing: Extract components from "Scientific_name_Common Name" format
- i18n layer: IOC multilingual translations with English fallback
"""

from dataclasses import dataclass
from typing import NamedTuple


class SpeciesComponents(NamedTuple):
    """Components of a parsed species name with IOC normalization."""

    scientific_name: str  # Primary key - immutable identifier
    common_name_tensor: str  # Raw common name from tensor model
    common_name_ioc: str  # IOC canonical English common name
    full_species: str  # Formatted as "IOC Common Name (Scientific Name)"


@dataclass
class SpeciesDisplayOptions:
    """Configuration for species display formatting with i18n support."""

    show_scientific_name: bool = True  # Whether to include scientific name
    show_common_name: bool = True  # Whether to include common name
    language_code: str = "en"  # Language for common name display
    format_template: str = "{common_name} ({scientific_name})"  # Display format
    fallback_to_tensor: bool = True  # Fallback to tensor name if IOC unavailable


class SpeciesParser:
    """Parser for species names from BirdNET tensor model output with IOC normalization."""

    def __init__(self, ioc_reference_service: "IOCReferenceService | None" = None):
        """Initialize parser with optional IOC reference service.

        Args:
            ioc_reference_service: Service for IOC species lookup and translation
        """
        self.ioc_reference = ioc_reference_service

    @staticmethod
    def parse_tensor_species(tensor_output: str) -> SpeciesComponents:
        """Parse species name from tensor model output format with IOC normalization.

        The tensor models output species in the format:
        "Scientific_name_Common Name" (e.g., "Abeillia abeillei_Emerald-chinned Hummingbird")

        This method extracts components and attempts IOC normalization using the scientific
        name as the primary key for lookup.

        Args:
            tensor_output: Raw species string from tensor model

        Returns:
            SpeciesComponents with scientific_name, tensor common_name, IOC common_name,
            and full_species

        Raises:
            ValueError: If the input format is invalid
        """
        if not tensor_output or not isinstance(tensor_output, str):
            raise ValueError("Invalid tensor output: must be a non-empty string")

        # Split on the underscore that separates scientific and common names
        parts = tensor_output.split("_", 1)

        if len(parts) != 2:
            raise ValueError(
                f"Invalid tensor species format: '{tensor_output}'. "
                "Expected format: 'Scientific_name_Common Name'"
            )

        scientific_name = parts[0].strip()
        common_name_tensor = parts[1].strip()

        if not scientific_name or not common_name_tensor:
            raise ValueError(f"Invalid species components in: '{tensor_output}'")

        # For now, use tensor common name as IOC placeholder until IOC service is implemented
        # TODO: Implement IOC lookup service to get canonical IOC English name
        common_name_ioc = common_name_tensor  # Placeholder - will be replaced by IOC lookup

        # Construct the full species name using IOC common name
        full_species = f"{common_name_ioc} ({scientific_name})"

        return SpeciesComponents(
            scientific_name=scientific_name,
            common_name_tensor=common_name_tensor,
            common_name_ioc=common_name_ioc,
            full_species=full_species,
        )

    @staticmethod
    def format_species_for_display(
        species_components: SpeciesComponents, display_options: SpeciesDisplayOptions
    ) -> str:
        """Format species components for display based on user preferences.

        Args:
            species_components: Parsed species components
            display_options: Display formatting preferences

        Returns:
            Formatted species string for display
        """
        if not display_options.show_common_name and not display_options.show_scientific_name:
            # Fallback to common name if both are disabled
            return species_components.common_name_ioc

        # Determine which common name to use based on language preferences
        # TODO: Implement IOC translation lookup for non-English languages
        common_name_display = species_components.common_name_ioc
        if display_options.language_code != "en" and display_options.fallback_to_tensor:
            # Placeholder: In future, lookup IOC translation for language_code
            # For now, fallback to IOC English
            common_name_display = species_components.common_name_ioc

        if display_options.show_common_name and not display_options.show_scientific_name:
            return common_name_display

        if not display_options.show_common_name and display_options.show_scientific_name:
            return species_components.scientific_name

        # Both enabled - use template
        return display_options.format_template.format(
            common_name=common_name_display,
            scientific_name=species_components.scientific_name,
            full_species=species_components.full_species,
        )

    @staticmethod
    def extract_common_name(tensor_output: str, prefer_ioc: bool = True) -> str:
        """Extract common name from tensor output, preferring IOC canonical name.

        Args:
            tensor_output: Raw species string from tensor model
            prefer_ioc: Whether to prefer IOC canonical name over tensor name

        Returns:
            Common name (IOC canonical if prefer_ioc=True, otherwise tensor)
        """
        components = SpeciesParser.parse_tensor_species(tensor_output)
        return components.common_name_ioc if prefer_ioc else components.common_name_tensor

    @staticmethod
    def extract_scientific_name(tensor_output: str) -> str:
        """Extract just the scientific name from tensor output.

        Args:
            tensor_output: Raw species string from tensor model

        Returns:
            Scientific name portion only
        """
        return SpeciesParser.parse_tensor_species(tensor_output).scientific_name

    @staticmethod
    def format_full_species(tensor_output: str) -> str:
        """Format tensor output as full species name.

        Args:
            tensor_output: Raw species string from tensor model

        Returns:
            Formatted full species as "Common Name (Scientific Name)"
        """
        return SpeciesParser.parse_tensor_species(tensor_output).full_species

    @staticmethod
    def is_valid_tensor_format(tensor_output: str) -> bool:
        """Check if a string is in valid tensor species format.

        Args:
            tensor_output: String to validate

        Returns:
            True if string matches expected tensor format
        """
        try:
            SpeciesParser.parse_tensor_species(tensor_output)
            return True
        except ValueError:
            return False


def create_display_options_from_config(config) -> SpeciesDisplayOptions:  # noqa: ANN001
    """Create SpeciesDisplayOptions from BirdNET configuration with i18n support.

    Args:
        config: BirdNETConfig instance with display preferences

    Returns:
        SpeciesDisplayOptions configured based on user preferences and language settings
    """
    # Get display and language preferences from config (to be added in next step)
    species_display_mode = getattr(config, "species_display_mode", "full")
    language_code = getattr(config, "language_code", "en")  # Default to English

    if species_display_mode == "common_name":
        return SpeciesDisplayOptions(
            show_scientific_name=False, show_common_name=True, language_code=language_code
        )
    elif species_display_mode == "scientific_name":
        return SpeciesDisplayOptions(
            show_scientific_name=True, show_common_name=False, language_code=language_code
        )
    else:  # 'full' or any other value defaults to full
        return SpeciesDisplayOptions(
            show_scientific_name=True,
            show_common_name=True,
            language_code=language_code,
            format_template="{common_name} ({scientific_name})",
        )


class IOCReferenceService:
    """Service for IOC World Bird Names lookup and translation.

    This service will be implemented to provide:
    - IOC canonical English common names lookup by scientific name
    - Multilingual translations from IOC spreadsheet data
    - Version tracking for IOC data updates
    - Fallback strategies for missing data
    """

    def __init__(self):
        """Initialize IOC reference service.

        TODO: Implement IOC data loading and caching
        """
        # Placeholder for IOC data structures
        self._ioc_reference = {}
        self._ioc_translations = {}
        self._ioc_version = "unknown"

    def get_ioc_common_name(self, scientific_name: str) -> str | None:
        """Get IOC canonical English common name for scientific name.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOC English common name or None if not found
        """
        # TODO: Implement IOC lookup
        return None

    def get_translated_common_name(self, scientific_name: str, language_code: str) -> str | None:
        """Get translated common name for scientific name and language.

        Args:
            scientific_name: Scientific name to lookup
            language_code: ISO language code (e.g., 'es', 'fr', 'de')

        Returns:
            Translated common name or None if not found
        """
        # TODO: Implement IOC translation lookup
        return None
