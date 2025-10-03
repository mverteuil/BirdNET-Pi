"""Multimedia API routes for serving audio and image files."""

import logging
from typing import Annotated
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.detections.models import AudioFile
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/audio/{audio_file_id}")
@inject
async def get_audio_file(
    audio_file_id: UUID,
    core_database: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> FileResponse:
    """Serve WAV audio file directly by audio file ID.

    This is more efficient than first looking up the detection.

    Args:
        audio_file_id: UUID of the audio file
        core_database: Database service for direct queries
        path_resolver: Path resolver for getting data directory paths

    Returns:
        FileResponse with the WAV audio file

    Raises:
        HTTPException: If audio file not found or missing on disk
    """
    try:
        async with core_database.get_async_db() as session:
            # Get audio file directly
            result = await session.execute(select(AudioFile).where(AudioFile.id == audio_file_id))
            audio_file = result.scalar_one_or_none()

            if not audio_file:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Audio file {audio_file_id} not found",
                )

            # Get the audio file path (stored relative to recordings directory)
            audio_path = audio_file.file_path

            # If path is relative, resolve it against the recordings directory
            if not audio_path.is_absolute():
                audio_path = path_resolver.get_recordings_dir() / audio_path

            # Check if file exists on disk
            if not audio_path.exists():
                logger.warning("Audio file not found on disk: %s", audio_path)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Audio file not found on disk",
                )

            # Serve the WAV file
            return FileResponse(
                path=audio_path,
                media_type="audio/wav",
                filename=audio_path.name,
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving audio file %s: %s", audio_file_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error serving audio file",
        ) from e
