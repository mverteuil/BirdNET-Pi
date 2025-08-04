import uuid
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
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

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:  # noqa: ANN401
        """Convert UUID to string for database storage."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:  # noqa: ANN401
        """Convert string back to UUID from database."""
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class Detection(Base):
    """Represents a bird detection record in the database."""

    __tablename__ = "detections"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)

    # Species identification (parsed from tensor output)
    species_tensor = Column(String, index=True)  # Raw tensor output: "Scientific_name_Common Name"
    scientific_name = Column(String(80), index=True)  # Parsed: "Genus species" (IOC primary key)
    common_name_tensor = Column(String(100))  # Parsed: tensor common name
    common_name_ioc = Column(String(100))  # IOC canonical English name (from attached IOC DB)

    # Detection metadata
    confidence = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    audio_file_id = Column(GUID(), ForeignKey("audio_files.id"), unique=True)
    audio_file = relationship("AudioFile", backref=backref("detection", uselist=False))

    # Location and analysis parameters
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    cutoff = Column(Float, nullable=True)
    week = Column(Integer, nullable=True)
    sensitivity = Column(Float, nullable=True)
    overlap = Column(Float, nullable=True)

    def get_display_name(self) -> str:
        """Get the best available species display name."""
        return str(self.common_name_ioc or self.common_name_tensor or self.scientific_name)


class AudioFile(Base):
    """Represents an audio file record in the database."""

    __tablename__ = "audio_files"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    file_path = Column(String, unique=True, index=True)
    duration = Column(Float)
    size_bytes = Column(Integer)
    recording_start_time = Column(DateTime(timezone=True))
    # Add more fields as needed
