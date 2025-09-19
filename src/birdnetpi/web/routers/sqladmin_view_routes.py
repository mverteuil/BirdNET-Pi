"""SQLAdmin configuration and setup for database administration interface."""

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.location.models import Weather
from birdnetpi.web.core.container import Container


class DetectionAdmin(ModelView, model=Detection):
    """Admin interface for Detection model."""

    name = "Detection"
    name_plural = "Detections"
    icon = "fa-solid fa-dove"

    # Using tuples (immutable) - parent class provides type annotations
    column_list = ("id", "scientific_name", "common_name", "confidence", "timestamp")
    column_searchable_list = ("scientific_name", "common_name")
    column_sortable_list = ("id", "confidence", "timestamp")
    column_default_sort = ("timestamp", True)
    page_size = 50
    page_size_options = (25, 50, 100, 200)


class AudioFileAdmin(ModelView, model=AudioFile):
    """Admin interface for AudioFile model."""

    name = "Audio File"
    name_plural = "Audio Files"
    icon = "fa-solid fa-file-audio"

    column_list = ("id", "file_path", "duration")
    column_searchable_list = ("file_path",)
    column_sortable_list = ("id", "duration")
    page_size = 50


class WeatherAdmin(ModelView, model=Weather):
    """Admin interface for Weather model."""

    name = "Weather"
    name_plural = "Weather Records"
    icon = "fa-solid fa-cloud-sun"

    column_list = (
        "timestamp",
        "latitude",
        "longitude",
        "temperature",
        "humidity",
        "wind_speed",
    )
    column_sortable_list = ("timestamp", "temperature", "humidity", "wind_speed")
    column_default_sort = ("timestamp", True)
    page_size = 50


def setup_sqladmin(app: FastAPI) -> Admin:
    """Set up SQLAdmin interface with all model views.

    Args:
        app: FastAPI application instance

    Returns:
        Configured Admin instance
    """
    # Get database engine from the DI container
    container = Container()
    core_database = container.core_database()

    # Create admin with custom configuration
    admin = Admin(
        app,
        core_database.async_engine,
        base_url="/admin/database",
        title="BirdNET-Pi Database Admin",
    )

    # Register model views
    admin.add_view(DetectionAdmin)
    admin.add_view(AudioFileAdmin)
    admin.add_view(WeatherAdmin)

    return admin
