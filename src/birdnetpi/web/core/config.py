"""Configuration management for the application with caching support."""

from functools import lru_cache

from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.system.path_resolver import PathResolver


@lru_cache
def get_config() -> BirdNETConfig:
    """Load BirdNET configuration with caching.

    Uses the existing ConfigManager which internally handles
    environment variables and PathResolver integration.
    The @lru_cache decorator ensures the configuration is loaded
    only once and cached for subsequent calls.

    Returns:
        BirdNETConfig: The loaded and validated configuration.
    """
    path_resolver = PathResolver()
    parser = ConfigManager(path_resolver)
    return parser.load()
