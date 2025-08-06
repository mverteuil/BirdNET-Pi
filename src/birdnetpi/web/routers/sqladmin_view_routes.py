"""SQLAdmin configuration and setup for database administration interface."""

from typing import ClassVar

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from birdnetpi.models.database_models import AudioFile, Detection


class DetectionAdmin(ModelView, model=Detection):
    """Admin interface for Detection model."""

    column_list: ClassVar = [
        Detection.id,
        Detection.scientific_name,
        Detection.common_name_ioc,
        Detection.confidence,
        Detection.timestamp,
    ]


class AudioFileAdmin(ModelView, model=AudioFile):
    """Admin interface for AudioFile model."""

    column_list: ClassVar = [
        AudioFile.id,
        AudioFile.file_path,
        AudioFile.duration,
        AudioFile.recording_start_time,
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
    database_service = container.database_service()
    
    admin = Admin(app, database_service.engine, base_url="/admin/database")

    # Register model views
    admin.add_view(DetectionAdmin)
    admin.add_view(AudioFileAdmin)

    return admin
