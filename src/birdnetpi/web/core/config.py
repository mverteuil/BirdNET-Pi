"""Configuration management for the application with caching support."""

from functools import lru_cache

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.config_file_parser import ConfigFileParser


@lru_cache
def get_config() -> BirdNETConfig:
    """Load BirdNET configuration with caching.

    Uses the existing ConfigFileParser which internally handles
    environment variables and PathResolver integration.
    The @lru_cache decorator ensures the configuration is loaded
    only once and cached for subsequent calls.

    Returns:
        BirdNETConfig: The loaded and validated configuration.
    """
    parser = ConfigFileParser()  # Uses existing PathResolver internally
    return parser.load_config()
