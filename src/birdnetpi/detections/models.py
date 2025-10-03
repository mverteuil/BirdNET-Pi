"""Database models for the detections domain."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import computed_field, field_serializer, model_serializer
from sqlalchemy import Column, Index, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.utils.field_type_annotations import PathType

if TYPE_CHECKING:
    from birdnetpi.location.models import Weather

# Import Weather at module level for SQLAlchemy relationship resolution
# This is needed because the relationship primaryjoin uses string references
# that SQLAlchemy needs to resolve at runtime
from birdnetpi.location.models import Weather


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

    # Weather at detection time (references composite key)
    weather_timestamp: datetime | None = Field(default=None, foreign_key="weather.timestamp")
    weather_latitude: float | None = Field(default=None, foreign_key="weather.latitude")
    weather_longitude: float | None = Field(default=None, foreign_key="weather.longitude")

    # Computed field for optimized JOINs (populated by trigger or application)
    hour_epoch: int | None = None  # Unix timestamp / 3600 for fast hour-based JOINs


class Detection(DetectionBase, table=True):
    """Represents a bird detection record in the database."""

    __tablename__: str = "detections"  # type: ignore[assignment]

    # Relationships
    audio_file: AudioFile = Relationship()  # type: ignore[assignment]
    weather: Weather | None = Relationship(
        sa_relationship=relationship(
            "Weather",
            back_populates="detections",
            primaryjoin=(
                "and_(Detection.weather_timestamp == Weather.timestamp, "
                "Detection.weather_latitude == Weather.latitude, "
                "Detection.weather_longitude == Weather.longitude)"
            ),
        )
    )  # type: ignore[assignment]

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
        # Hour-based indexes for 256x speedup on weather correlation queries
        Index("idx_detections_hour_epoch", "hour_epoch"),
        Index("idx_detections_timestamp_hour", "timestamp", "hour_epoch"),
        Index("idx_detections_hour_species", "hour_epoch", "scientific_name"),
    )


class DetectionWithTaxa(DetectionBase):
    """Detection with additional taxonomy information.

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

    # First detection metadata (optional, populated when requested)
    is_first_ever: bool | None = None
    is_first_in_period: bool | None = None
    first_ever_detection: datetime | None = None
    first_period_detection: datetime | None = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        """Serialize timestamp to ISO format."""
        return value.isoformat() if value else ""

    @field_serializer("first_ever_detection", "first_period_detection")
    def serialize_datetime_fields(self, value: datetime | None) -> str | None:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    @field_serializer("id")
    def serialize_id(self, value: uuid.UUID) -> str:
        """Serialize UUID to string."""
        return str(value)

    @field_serializer("confidence")
    def serialize_confidence(self, value: float) -> float:
        """Round confidence to 2 decimal places."""
        return round(value, 2) if value is not None else 0.0

    @computed_field  # type: ignore[misc]
    @property
    def date(self) -> str:
        """Get the date portion of timestamp."""
        return self.timestamp.strftime("%Y-%m-%d") if self.timestamp else ""

    @computed_field  # type: ignore[misc]
    @property
    def time(self) -> str:
        """Get the time portion of timestamp."""
        return self.timestamp.strftime("%H:%M") if self.timestamp else ""

    @model_serializer(mode="wrap")
    def serialize_model(self, serializer: object, info: object) -> dict[str, Any]:
        """Serialize model with config-aware display name computation.

        This allows us to pass config through context to compute
        the proper display name based on configuration rules.
        Also provides backward compatibility by setting common_name.
        """
        # Get the default serialization
        data = serializer(self)  # type: ignore[operator]

        # Check if we have context with config
        if info and hasattr(info, "context") and info.context:  # type: ignore[attr-defined]
            config = info.context.get("config")  # type: ignore[attr-defined]

            if config:
                # Create a display service with the config and use it
                display_service = SpeciesDisplayService(config)
                # Always prefer translation (as recommended)
                display_name = display_service.format_species_display(self, prefer_translation=True)

                # Set both display_name and common_name for backward compatibility
                data["display_name"] = display_name
                # Override common_name with the properly formatted display name
                data["common_name"] = display_name

        return data

    def __init__(
        self,
        detection: Detection | None = None,
        ioc_english_name: str | None = None,
        translated_name: str | None = None,
        family: str | None = None,
        genus: str | None = None,
        order_name: str | None = None,
        is_first_ever: bool | None = None,
        is_first_in_period: bool | None = None,
        first_ever_detection: datetime | None = None,
        first_period_detection: datetime | None = None,
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

        # Set first detection fields
        self.is_first_ever = is_first_ever
        self.is_first_in_period = is_first_in_period
        self.first_ever_detection = first_ever_detection
        self.first_period_detection = first_period_detection

    @property
    def detection(self) -> DetectionBase:
        """Return self as Detection for backward compatibility."""
        return self

    def __eq__(self, other: object) -> bool:
        """Compare DetectionWithLocalization objects for equality."""
        if not isinstance(other, DetectionWithTaxa):
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
