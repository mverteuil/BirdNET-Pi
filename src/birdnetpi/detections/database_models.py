"""Database models for the detections domain."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import func

# Import AudioFile from audio domain (for relationship reference)
from birdnetpi.audio.models import AudioFile  # noqa: F401
from birdnetpi.database.model_utils import GUID, Base


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
