"""Database models for the audio domain."""

import uuid

from sqlalchemy import Column, Float, Integer

from birdnetpi.database.model_utils import GUID, Base, PathType


class AudioFile(Base):
    """Represents an audio file record in the database."""

    __tablename__ = "audio_files"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, index=True)
    file_path = Column(PathType, unique=True, index=True, nullable=False)
    duration = Column(Float)
    size_bytes = Column(Integer)
