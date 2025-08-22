"""SQLAlchemy models for IOC World Bird Names reference database.

This module defines the database schema for the IOC reference data,
which is stored separately from the main detections database but can
be queried using SQLite's ATTACH DATABASE functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class IOCSpecies(SQLModel, table=True):
    """IOC species reference table with canonical data."""

    __tablename__: str = "species"  # type: ignore[assignment]

    scientific_name: str = Field(
        sa_column=Column(String(80), primary_key=True)
    )  # e.g., "Turdus migratorius"
    english_name: str = Field(sa_column=Column(String(80)))  # e.g., "American Robin"
    order_name: str = Field(sa_column=Column(String(30)))  # e.g., "PASSERIFORMES"
    family: str = Field(sa_column=Column(String(30)))  # e.g., "Turdidae"
    genus: str = Field(sa_column=Column(String(30)))  # e.g., "Turdus"
    species_epithet: str = Field(sa_column=Column(String(30)))  # e.g., "migratorius"
    authority: str | None = Field(
        default=None, sa_column=Column(String(60))
    )  # e.g., "Linnaeus, 1766"
    breeding_regions: str | None = Field(default=None, sa_column=Column(String(20)))  # e.g., "NA"
    breeding_subregions: str | None = Field(
        default=None, sa_column=Column(String(200))
    )  # e.g., "n,c,e"

    # Relationships - One-to-many: one species has many translations
    # NOTE: Relationships commented out because IOC database is attached separately
    # and relationships are not used in the application
    # translations: list = Relationship()  # type: ignore[assignment, type-arg]


class IOCTranslation(SQLModel, table=True):
    """IOC species translations for multilingual support."""

    __tablename__: str = "translations"  # type: ignore[assignment]
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: int | None = Field(default=None, primary_key=True)
    scientific_name: str = Field(foreign_key="species.scientific_name")
    language_code: str = Field(sa_column=Column(String(8)))  # e.g., "es", "fr", "zh-TW"
    common_name: str = Field(sa_column=Column(String(120)))  # e.g., "Zorzal robín"

    # Relationships - Many-to-one: many translations belong to one species
    # NOTE: Relationships commented out because IOC database is attached separately
    # and relationships are not used in the application
    # species: IOCSpecies = Relationship()  # type: ignore[assignment]


class IOCMetadata(SQLModel, table=True):
    """Metadata about the IOC reference database."""

    __tablename__: str = "metadata"  # type: ignore[assignment]

    key: str = Field(sa_column=Column(String(50), primary_key=True))
    value: str = Field(sa_column=Column(String(200)))

    # Common keys:
    # - 'ioc_version': '15.1'
    # - 'created_at': '2025-01-15T10:30:00Z'
    # - 'species_count': '11250'
    # - 'translation_count': '296998'
    # - 'languages_available': 'en,es,fr,de,zh,ja,...'


class IOCLanguage(SQLModel, table=True):
    """Available languages in the IOC reference database."""

    __tablename__: str = "languages"  # type: ignore[assignment]

    language_code: str = Field(sa_column=Column(String(10), primary_key=True))  # e.g., "es"
    language_name: str = Field(sa_column=Column(String(50)))  # e.g., "Spanish"
    language_family: str | None = Field(
        default=None, sa_column=Column(String(30))
    )  # e.g., "Romance"
    translation_count: int = Field(default=0)  # Number of translations available

    # Example entries:
    # ('en', 'English', 'Germanic', 11250)
    # ('es', 'Spanish', 'Romance', 8943)
    # ('zh', 'Chinese', 'Sino-Tibetan', 9876)
