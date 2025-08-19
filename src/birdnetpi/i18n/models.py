"""SQLModel models for attached multilingual databases.

These models are only used for querying already-attached databases via ATTACH DATABASE.
They use table=False to prevent SQLModel from trying to create these tables.
The schema names (ioc, avibase, patlevin) are included in the __tablename__ for queries.
"""

from __future__ import annotations

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


# IOC Database Models (attached via ATTACH DATABASE)
class IOCSpeciesAttached(SQLModel, table=False):
    """IOC species table in attached database.

    This model is only for querying - the table already exists in the attached IOC database.
    """

    __tablename__: str = "ioc.species"  # type: ignore[assignment]

    scientific_name: str = Field(sa_column=Column(String(80), primary_key=True))
    english_name: str = Field(sa_column=Column(String(80)))


class IOCTranslationAttached(SQLModel, table=False):
    """IOC translations table in attached database.

    This model is only for querying - the table already exists in the attached IOC database.
    """

    __tablename__: str = "ioc.translations"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    scientific_name: str = Field(sa_column=Column(String(80)))
    language_code: str = Field(sa_column=Column(String(10)))
    common_name: str = Field(sa_column=Column(String(100)))


# PatLevin Database Models (attached via ATTACH DATABASE)
class PatLevinLabel(SQLModel, table=False):
    """PatLevin BirdNET labels table in attached database.

    This model is only for querying - the table already exists in the attached PatLevin database.
    """

    __tablename__: str = "patlevin.patlevin_labels"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    scientific_name: str = Field(sa_column=Column(String(80)))
    language_code: str = Field(sa_column=Column(String(10)))
    common_name: str = Field(sa_column=Column(String(100)))


# Avibase Database Models (attached via ATTACH DATABASE)
class AvibaseName(SQLModel, table=False):
    """Avibase names table in attached database.

    This model is only for querying - the table already exists in the attached Avibase database.
    """

    __tablename__: str = "avibase.avibase_names"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    scientific_name: str = Field(sa_column=Column(String(80)))
    language_code: str = Field(sa_column=Column(String(10)))
    common_name: str = Field(sa_column=Column(String(100)))
