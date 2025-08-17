"""Database model utilities including Base class and type decorators."""

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import CHAR
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import String, TypeDecorator

# Create the shared declarative base for all domain models
Base = declarative_base()


class GUID(TypeDecorator):
    """SQLite-compatible GUID type using CHAR(36) storage."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:  # noqa: ANN401
        """Load CHAR(36) for all database types."""
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:  # noqa: ANN401
        """Convert UUID to string for database storage."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:  # noqa: ANN401
        """Convert string back to UUID from database."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


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
