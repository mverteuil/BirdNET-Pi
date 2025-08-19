"""Database model utilities including type decorators.

With SQLModel, we don't need a separate Base class - SQLModel provides that.
"""

from pathlib import Path
from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import String, TypeDecorator


class PathType(TypeDecorator):
    """Type decorator for Path objects.

    Stores paths as strings in the database but provides Path objects in Python.
    Validates that paths are not empty or blank.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:  # noqa: ANN401
        """Convert Path to string for database storage."""
        if value is None:
            raise ValueError("Path cannot be None")

        if isinstance(value, Path):
            path_str = str(value)
        else:
            path_str = str(value)

        # Validate non-empty
        if not path_str or not path_str.strip():
            raise ValueError("Path cannot be empty or blank")

        return path_str

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:  # noqa: ANN401
        """Convert string back to Path from database."""
        if value is None:
            # This shouldn't happen with nullable=False, but handle gracefully
            raise ValueError("Path value from database cannot be None")
        return Path(value)
