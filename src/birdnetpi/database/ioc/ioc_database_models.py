"""SQLAlchemy models for IOC World Bird Names reference database.

This module defines the database schema for the IOC reference data,
which is stored separately from the main detections database but can
be queried using SQLite's ATTACH DATABASE functionality.
"""

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

# Separate base for IOC reference database
IOCBase = declarative_base()


class IOCSpecies(IOCBase):
    """IOC species reference table with canonical data."""

    __tablename__ = "species"

    scientific_name = Column(String(80), primary_key=True)  # e.g., "Turdus migratorius"
    english_name = Column(String(80), nullable=False)  # e.g., "American Robin"
    order_name = Column(String(30), nullable=False)  # e.g., "PASSERIFORMES"
    family = Column(String(30), nullable=False)  # e.g., "Turdidae"
    genus = Column(String(30), nullable=False)  # e.g., "Turdus"
    species_epithet = Column(String(30), nullable=False)  # e.g., "migratorius"
    authority = Column(String(60), nullable=True)  # e.g., "Linnaeus, 1766"
    breeding_regions = Column(String(20), nullable=True)  # e.g., "NA"
    breeding_subregions = Column(String(200), nullable=True)  # e.g., "n,c,e"

    # Relationships
    translations = relationship("IOCTranslation", back_populates="species")


class IOCTranslation(IOCBase):
    """IOC species translations for multilingual support."""

    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scientific_name = Column(
        String(80),
        ForeignKey("species.scientific_name", ondelete="CASCADE"),
        nullable=False,
    )
    language_code = Column(String(8), nullable=False)  # e.g., "es", "fr", "zh-TW"
    common_name = Column(String(120), nullable=False)  # e.g., "Zorzal robín"

    # Relationships
    species = relationship("IOCSpecies", back_populates="translations")

    __table_args__ = ({"sqlite_autoincrement": True},)


class IOCMetadata(IOCBase):
    """Metadata about the IOC reference database."""

    __tablename__ = "metadata"

    key = Column(String(50), primary_key=True)
    value = Column(String(200), nullable=False)

    # Common keys:
    # - 'ioc_version': '15.1'
    # - 'created_at': '2025-01-15T10:30:00Z'
    # - 'species_count': '11250'
    # - 'translation_count': '296998'
    # - 'languages_available': 'en,es,fr,de,zh,ja,...'


class IOCLanguage(IOCBase):
    """Available languages in the IOC reference database."""

    __tablename__ = "languages"

    language_code = Column(String(10), primary_key=True)  # e.g., "es"
    language_name = Column(String(50), nullable=False)  # e.g., "Spanish"
    language_family = Column(String(30), nullable=True)  # e.g., "Romance"
    translation_count = Column(
        Integer, nullable=False, default=0
    )  # Number of translations available

    # Example entries:
    # ('en', 'English', 'Germanic', 11250)
    # ('es', 'Spanish', 'Romance', 8943)
    # ('zh', 'Chinese', 'Sino-Tibetan', 9876)
