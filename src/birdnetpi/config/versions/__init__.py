"""Configuration version definitions.

Each version module contains the complete specification for that config version:
- Default values
- Validation rules
- Upgrade logic from previous version
"""

from .registry import VersionRegistry

__all__ = ["VersionRegistry"]
