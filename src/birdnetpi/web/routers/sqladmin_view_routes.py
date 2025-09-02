"""SQLAdmin configuration and setup for database administration interface."""

from typing import ClassVar

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.location.models import Weather


class DetectionAdmin(ModelView, model=Detection):
    """Admin interface for Detection model."""

    column_list: ClassVar[list[str]] = [  # type: ignore[assignment]
        "id",
        "scientific_name",
        "common_name",
        "confidence",
        "timestamp",
    ]


class AudioFileAdmin(ModelView, model=AudioFile):
    """Admin interface for AudioFile model."""

    column_list: ClassVar[list[str]] = [  # type: ignore[assignment]
        "id",
        "file_path",
        "duration",
    ]


class WeatherAdmin(ModelView, model=Weather):
    """Admin interface for Weather model."""

    column_list: ClassVar[list[str]] = [  # type: ignore[assignment]
        "timestamp",
        "latitude",
        "longitude",
        "temperature",
        "humidity",
        "wind_speed",
    ]


def setup_sqladmin(app: FastAPI) -> Admin:
    """Set up SQLAdmin interface with all model views.

    Args:
        app: FastAPI application instance

    Returns:
        Configured Admin instance
    """
    # Get database engine from the DI container
    container = app.container  # type: ignore[attr-defined]
    bnp_database_service = container.bnp_database_service()

    # SQLAdmin supports async engines
    admin = Admin(app, bnp_database_service.async_engine, base_url="/admin/database")

    # Register model views
    admin.add_view(DetectionAdmin)
    admin.add_view(AudioFileAdmin)
    admin.add_view(WeatherAdmin)

    return admin
