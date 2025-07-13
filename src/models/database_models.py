from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    species = Column(String, index=True)
    confidence = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    audio_file_path = Column(String)
    spectrogram_path = Column(String, nullable=True)
    # Add more fields as needed, e.g., latitude, longitude, site_name from config


class AudioFile(Base):
    __tablename__ = "audio_files"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, unique=True, index=True)
    duration = Column(Float)
    size_bytes = Column(Integer)
    recording_start_time = Column(DateTime(timezone=True))
    # Add more fields as needed
