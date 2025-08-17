"""BirdNET-Pi configuration package.

This package provides centralized configuration management with:
- Version tracking and migration support
- Validation for each config version
- Smart defaults management
- YAML parsing and serialization
"""

from .manager import ConfigManager
from .models import BirdNETConfig

__all__ = [
    "BirdNETConfig",
    "ConfigManager",
]
