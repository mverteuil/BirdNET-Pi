"""Configuration management for the application with caching support."""

from birdnetpi.config import BirdNETConfig, ConfigManager
from birdnetpi.system.path_resolver import PathResolver


def get_config(path_resolver: PathResolver | None = None) -> BirdNETConfig:
    """Load BirdNET configuration.

    Uses the existing ConfigManager which internally handles
    environment variables and PathResolver integration.

    Args:
        path_resolver: Optional PathResolver instance to use. If not provided,
                      creates a new PathResolver instance.

    Returns:
        BirdNETConfig: The loaded and validated configuration.
    """
    if path_resolver is None:
        path_resolver = PathResolver()
    parser = ConfigManager(path_resolver)
    return parser.load()
