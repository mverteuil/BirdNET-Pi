"""Database models for location and weather data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Index, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from birdnetpi.detections.models import Detection


class Weather(SQLModel, table=True):
    """Weather conditions at detection time."""

    __tablename__: str = "weather"  # type: ignore[assignment]

    # Natural composite key: timestamp + location
    timestamp: datetime = Field(primary_key=True)
    latitude: float = Field(primary_key=True)
    longitude: float = Field(primary_key=True)

    # Basic conditions
    temperature: float | None = None  # Celsius
    humidity: float | None = None  # Percentage
    pressure: float | None = None  # hPa

    # Wind
    wind_speed: float | None = None  # km/h
    wind_direction: int | None = None  # Degrees

    # Precipitation
    precipitation: float | None = None  # mm
    rain: float | None = None  # mm
    snow: float | None = None  # mm

    # Sky conditions
    cloud_cover: int | None = None  # Percentage
    visibility: float | None = None  # km

    # Descriptive
    weather_code: int | None = None  # WMO weather code
    conditions: str | None = Field(
        default=None, sa_column=Column(String(50))
    )  # "Clear", "Rainy", etc.

    # Solar (affects bird activity)
    uv_index: float | None = None
    solar_radiation: float | None = None  # W/m²

    # Source tracking
    source: str | None = Field(
        default=None, sa_column=Column(String(20))
    )  # "open-meteo", "cache", etc.
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationship to detections using explicit SQLAlchemy relationship
    detections: list[Detection] = Relationship(
        sa_relationship=relationship(
            "Detection",
            back_populates="weather",
            primaryjoin=(
                "and_(Detection.weather_timestamp == Weather.timestamp, "
                "Detection.weather_latitude == Weather.latitude, "
                "Detection.weather_longitude == Weather.longitude)"
            ),
            uselist=True,
        )
    )  # type: ignore[assignment]

    # Indexes for common queries
    __table_args__ = (
        Index("idx_weather_timestamp", "timestamp"),
        Index("idx_weather_conditions", "temperature", "wind_speed", "precipitation"),
    )
