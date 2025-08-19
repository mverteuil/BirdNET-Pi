"""Database models for the detections domain."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Column, Index, String
from sqlmodel import Field, Relationship, SQLModel

from birdnetpi.utils.field_type_annotations import PathType

if TYPE_CHECKING:
    pass


class AudioFile(SQLModel, table=True):
    """Represents an audio file record in the database."""

    __tablename__: str = "audio_files"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    file_path: Path = Field(sa_column=Column(PathType, unique=True, index=True))
    duration: float | None = None
    size_bytes: int | None = None


class DetectionBase(SQLModel):
    """Base class for detection models without relationships."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)

    # Species identification (parsed from tensor output)
    species_tensor: str = Field(index=True)  # Raw tensor output: "Scientific_name_Common Name"
    scientific_name: str = Field(
        sa_column=Column(String(80), index=True)
    )  # Parsed: "Genus species" (IOC primary key)
    common_name: str | None = Field(
        default=None, sa_column=Column(String(100))
    )  # Common name (IOC preferred, tensor fallback)

    # Detection metadata
    confidence: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    audio_file_id: uuid.UUID | None = Field(default=None, foreign_key="audio_files.id", unique=True)

    # Location and analysis parameters
    latitude: float | None = None
    longitude: float | None = None
    species_confidence_threshold: float | None = None  # Species confidence threshold
    week: int | None = None
    sensitivity_setting: float | None = None  # Analysis sensitivity setting
    overlap: float | None = (
        None  # Audio analysis window overlap (0.0-1.0) for signal processing continuity
    )


class Detection(DetectionBase, table=True):
    """Represents a bird detection record in the database."""

    __tablename__: str = "detections"  # type: ignore[assignment]

    # Relationship - One-to-one (unique foreign key)
    audio_file: AudioFile = Relationship()  # type: ignore[assignment]

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


class DetectionWithLocalization(DetectionBase):
    """Detection with additional localization information.

    This is a non-table model that extends DetectionBase with IOC taxonomy data.
    It's used for runtime data enrichment without persisting to database.
    By inheriting from DetectionBase, we avoid relationship field issues.
    """

    # Additional fields for localization
    ioc_english_name: str | None = None
    translated_name: str | None = None
    family: str | None = None
    genus: str | None = None
    order_name: str | None = None

    def __init__(
        self,
        detection: Detection | None = None,
        ioc_english_name: str | None = None,
        translated_name: str | None = None,
        family: str | None = None,
        genus: str | None = None,
        order_name: str | None = None,
        **kwargs,  # noqa: ANN003
    ):
        """Initialize with a detection and localization data.

        Can be initialized either with a Detection object or with individual fields.
        """
        if detection:
            # Copy all fields from the detection
            super().__init__(
                id=detection.id,
                species_tensor=detection.species_tensor,
                scientific_name=detection.scientific_name,
                common_name=detection.common_name,
                confidence=detection.confidence,
                timestamp=detection.timestamp,
                audio_file_id=detection.audio_file_id,
                latitude=detection.latitude,
                longitude=detection.longitude,
                species_confidence_threshold=detection.species_confidence_threshold,
                week=detection.week,
                sensitivity_setting=detection.sensitivity_setting,
                overlap=detection.overlap,
            )
        else:
            # Initialize from kwargs
            super().__init__(**kwargs)

        # Set localization fields
        self.ioc_english_name = ioc_english_name
        self.translated_name = translated_name
        self.family = family
        self.genus = genus
        self.order_name = order_name

    @property
    def detection(self) -> DetectionBase:
        """Return self as Detection for backward compatibility."""
        return self

    def __eq__(self, other: object) -> bool:
        """Compare DetectionWithLocalization objects for equality."""
        if not isinstance(other, DetectionWithLocalization):
            return False

        # Compare all detection base fields
        return (
            self.id == other.id
            and self.species_tensor == other.species_tensor
            and self.scientific_name == other.scientific_name
            and self.common_name == other.common_name
            and self.confidence == other.confidence
            and self.timestamp == other.timestamp
            and self.audio_file_id == other.audio_file_id
            and self.latitude == other.latitude
            and self.longitude == other.longitude
            and self.species_confidence_threshold == other.species_confidence_threshold
            and self.week == other.week
            and self.sensitivity_setting == other.sensitivity_setting
            and self.overlap == other.overlap
            and self.ioc_english_name == other.ioc_english_name
            and self.translated_name == other.translated_name
            and self.family == other.family
            and self.genus == other.genus
            and self.order_name == other.order_name
        )
