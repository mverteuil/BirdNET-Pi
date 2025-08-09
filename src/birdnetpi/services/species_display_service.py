"""Species display formatting service for BirdNET-Pi.

This service handles all species name display formatting based on user configuration,
providing a clean separation between data objects and presentation logic.
"""

from typing import TYPE_CHECKING

from birdnetpi.models.config import BirdNETConfig

if TYPE_CHECKING:
    from birdnetpi.services.detection_query_service import DetectionWithLocalization


class SpeciesDisplayService:
    """Service for formatting species names based on user preferences and configuration."""

    def __init__(self, config: BirdNETConfig):
        """Initialize species display service.

        Args:
            config: BirdNET configuration containing display preferences
        """
        self.config = config

    def format_species_display(
        self, detection: "DetectionWithLocalization", prefer_translation: bool = False
    ) -> str:
        """Format species name based on configuration and preferences.

        Args:
            detection: Detection object with localization data
            prefer_translation: Whether to prefer translated names over IOC English names

        Returns:
            Formatted species name respecting user's display mode preference
        """
        # If user prefers scientific names only, return scientific name
        if self.config.species_display_mode == "scientific_name":
            return detection.scientific_name

        # Handle common name selection logic
        if prefer_translation:
            # Prefer translation first, then IOC, then fallback
            if detection.translated_name:
                return detection.translated_name
            if detection.ioc_english_name:
                return detection.ioc_english_name
        else:
            # Prefer IOC first, then translation, then fallback
            if detection.ioc_english_name:
                return detection.ioc_english_name
            if detection.translated_name:
                return detection.translated_name

        # Final fallback to original common name or scientific name
        return detection.common_name or detection.scientific_name

    def format_full_species_display(
        self, detection: "DetectionWithLocalization", prefer_translation: bool = False
    ) -> str:
        """Format full species display based on configuration.

        Args:
            detection: Detection object with localization data
            prefer_translation: Whether to prefer translated names over IOC English names

        Returns:
            Full formatted species display respecting user's display mode:
            - "scientific_name": Just scientific name
            - "common_name": Just common name
            - "full": "Common Name (Scientific Name)"
        """
        if self.config.species_display_mode == "scientific_name":
            return detection.scientific_name
        elif self.config.species_display_mode == "common_name":
            return self.format_species_display(detection, prefer_translation)
        else:  # "full" mode
            common_name = self.format_species_display(detection, prefer_translation)
            return f"{common_name} ({detection.scientific_name})"

    def get_display_mode(self) -> str:
        """Get current species display mode from configuration.

        Returns:
            Current species display mode: "scientific_name", "common_name", or "full"
        """
        return self.config.species_display_mode

    def should_show_scientific_name(self) -> bool:
        """Check if scientific names should be shown in current display mode.

        Returns:
            True if scientific names should be displayed
        """
        return self.config.species_display_mode in ("scientific_name", "full")

    def should_show_common_name(self) -> bool:
        """Check if common names should be shown in current display mode.

        Returns:
            True if common names should be displayed
        """
        return self.config.species_display_mode in ("common_name", "full")
