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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from birdnetpi.database.species import SpeciesDatabaseService


class SpeciesComponents(NamedTuple):
    """Components of a parsed species name with standardized naming."""

    scientific_name: str  # Primary key - immutable identifier
    common_name: str  # Standardized common name from tensor model
    full_species: str  # Formatted as "Common Name (Scientific Name)"


@dataclass
class SpeciesDisplayOptions:
    """Configuration for species display formatting with i18n support."""

    show_scientific_name: bool = True  # Whether to include scientific name
    show_common_name: bool = True  # Whether to include common name
    language_code: str = "en"  # Language for common name display
    format_template: str = "{common_name} ({scientific_name})"  # Display format
    fallback_to_common: bool = True  # Always use standardized common name


class SpeciesParser:
    """Parser for species names from BirdNET tensor model output with IOC normalization."""

    # Class-level instance for global access
    _instance: "SpeciesParser | None" = None
    # Class-level session for database queries
    _session: "AsyncSession | None" = None

    def __init__(self, species_database: "SpeciesDatabaseService"):
        """Initialize parser with required multilingual database service.

        Args:
            species_database: Service for multilingual species lookup (required)

        Raises:
            TypeError: If species_database is None
        """
        if species_database is None:
            raise TypeError("SpeciesDatabaseService is required for SpeciesParser")

        self.species_database = species_database
        # Set as global instance if none exists
        if SpeciesParser._instance is None:
            SpeciesParser._instance = self

    @classmethod
    def _get_parser_instance(cls) -> "SpeciesParser | None":
        """Get the global parser instance for IOC lookups."""
        return cls._instance

    @classmethod
    def set_session(cls, session: "AsyncSession") -> None:
        """Set the database session for species lookups.

        Args:
            session: AsyncSession with multilingual databases attached
        """
        cls._session = session

    async def get_ioc_common_name(self, scientific_name: str) -> str | None:
        """Get IOC canonical common name from multilingual database service.

        Uses the multilingual database service to get the best available common name,
        prioritizing IOC English names.

        Args:
            scientific_name: Scientific name to look up

        Returns:
            IOC English common name or None if species not found
        """
        if not self._session:
            return None

        # Get best common name with English preference (IOC priority)
        result = await self.species_database.get_best_common_name(
            self._session, scientific_name, language_code="en"
        )
        return result.get("common_name")

    @staticmethod
    async def parse_tensor_species(tensor_output: str) -> SpeciesComponents:
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
        common_name = parts[1].strip()

        if not scientific_name or not common_name:
            raise ValueError(f"Invalid species components in: '{tensor_output}'")

        # For now, use the tensor common name from BirdNET labels as the source of truth
        # IOC taxonomy differs from BirdNET taxonomy (e.g., IOC has "Mangrove Warbler"
        # for Setophaga petechia while BirdNET has "Yellow Warbler")
        # TODO: Make this configurable - allow users to choose between BirdNET or IOC taxonomy
        final_common_name = common_name

        # Optionally check IOC for additional metadata but don't override common name
        if parser_instance := SpeciesParser._get_parser_instance():
            ioc_common_name = await parser_instance.get_ioc_common_name(scientific_name)
            # Log if there's a mismatch for debugging
            if ioc_common_name and ioc_common_name != common_name:
                logger.debug(
                    f"Taxonomy mismatch for {scientific_name}: "
                    f"BirdNET='{common_name}', IOC='{ioc_common_name}'"
                )

        # Construct the full species name using the best available common name
        full_species = f"{final_common_name} ({scientific_name})"

        return SpeciesComponents(
            scientific_name=scientific_name,
            common_name=final_common_name,
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
            return species_components.common_name

        # Determine which common name to use based on language preferences
        # TODO: Implement IOC translation lookup for non-English languages
        common_name_display = species_components.common_name
        if display_options.language_code != "en" and display_options.fallback_to_common:
            # Placeholder: In future, lookup IOC translation for language_code
            # For now, fallback to IOC English
            common_name_display = species_components.common_name

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
    async def extract_common_name(tensor_output: str, prefer_ioc: bool = True) -> str:
        """Extract common name from tensor output, preferring IOC canonical name.

        Args:
            tensor_output: Raw species string from tensor model
            prefer_ioc: Whether to prefer IOC canonical name over tensor name

        Returns:
            Common name (IOC canonical if prefer_ioc=True, otherwise tensor)
        """
        components = await SpeciesParser.parse_tensor_species(tensor_output)
        return components.common_name

    @staticmethod
    async def extract_scientific_name(tensor_output: str) -> str:
        """Extract just the scientific name from tensor output.

        Args:
            tensor_output: Raw species string from tensor model

        Returns:
            Scientific name portion only
        """
        components = await SpeciesParser.parse_tensor_species(tensor_output)
        return components.scientific_name

    @staticmethod
    async def format_full_species(tensor_output: str) -> str:
        """Format tensor output as full species name.

        Args:
            tensor_output: Raw species string from tensor model

        Returns:
            Formatted full species as "Common Name (Scientific Name)"
        """
        components = await SpeciesParser.parse_tensor_species(tensor_output)
        return components.full_species

    @staticmethod
    async def is_valid_tensor_format(tensor_output: str) -> bool:
        """Check if a string is in valid tensor species format.

        Args:
            tensor_output: String to validate

        Returns:
            True if string matches expected tensor format
        """
        try:
            await SpeciesParser.parse_tensor_species(tensor_output)
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
    # Get display and language preferences from config
    species_display_mode = config.species_display_mode
    language_code = config.language

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
