"""Database models for the detections domain."""

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import backref, declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import CHAR, TypeDecorator

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


class Detection(Base):
    """Represents a bird detection record in the database."""

    __tablename__ = "detections"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, index=True)

    # Species identification (parsed from tensor output)
    species_tensor = Column(String, index=True)  # Raw tensor output: "Scientific_name_Common Name"
    scientific_name = Column(String(80), index=True)  # Parsed: "Genus species" (IOC primary key)
    common_name = Column(String(100))  # Common name (IOC preferred, tensor fallback)

    # Detection metadata
    confidence = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.utcnow(), index=True)
    audio_file_id = Column(GUID, ForeignKey("audio_files.id"), unique=True)
    audio_file = relationship("AudioFile", backref=backref("detection", uselist=False))

    # Location and analysis parameters
    latitude = Column(Float)
    longitude = Column(Float)
    species_confidence_threshold = Column(Float)  # Species confidence threshold
    week = Column(Integer)
    sensitivity_setting = Column(Float)  # Analysis sensitivity setting
    overlap = Column(
        Float
    )  # Audio analysis window overlap (0.0-1.0) for signal processing continuity

    def get_display_name(self) -> str:
        """Get the best available species display name."""
        return str(self.common_name or self.scientific_name)

    # Indexes for JOIN performance optimization
    __table_args__ = (
        # Composite index for common query patterns
        Index("idx_detections_timestamp_species", "timestamp", "scientific_name"),
        # Index for filtering by confidence and species
        Index("idx_detections_confidence_species", "confidence", "scientific_name"),
        # Index for date range queries with family filtering (requires JOIN)
        Index("idx_detections_timestamp_confidence", "timestamp", "confidence"),
    )


class AudioFile(Base):
    """Represents an audio file record in the database."""

    __tablename__ = "audio_files"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, index=True)
    file_path = Column(PathType, unique=True, index=True, nullable=False)
    duration = Column(Float)
    size_bytes = Column(Integer)
