import logging
from datetime import UTC, date, datetime
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

from birdnetpi.analytics.plotting_manager import PlottingManager
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.models import DetectionEvent, LocationUpdate
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
@inject
async def create_detection(
    detection_event: DetectionEvent,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> dict:
    """Receive a new detection event and dispatch it."""
    logger.info(
        f"Received detection: {detection_event.species_tensor or 'Unknown'} "
        f"with confidence {detection_event.confidence}"
    )

    # Create detection - the @emit_detection_event decorator handles event emission
    saved_detection = data_manager.create_detection(detection_event)

    return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}


@router.get("/recent")
@inject
async def get_recent_detections(
    limit: int = 10,
    offset: int = 0,  # Added for compatibility with old endpoint
    language_code: str = "en",
    include_l10n: bool = True,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Get recent bird detections with optional translation data."""
    try:
        if include_l10n:
            # Use DataManager for localization-enhanced data
            detections = data_manager.query_detections(
                limit=limit,
                offset=offset,
                order_by="timestamp",
                order_desc=True,
                include_localization=True,
                language_code=language_code,
            )
            detection_list = [
                {
                    "id": detection.id if hasattr(detection, "id") else detection.detection.id,
                    "scientific_name": detection.scientific_name,
                    "common_name": (
                        data_manager.get_species_display_name(detection, True, language_code)
                        if hasattr(detection, "ioc_english_name")
                        else detection.common_name
                    ),
                    "confidence": detection.confidence,
                    "timestamp": detection.timestamp.isoformat(),
                    "latitude": (
                        detection.detection.latitude if hasattr(detection, "detection") else None
                    ),
                    "longitude": (
                        detection.detection.longitude if hasattr(detection, "detection") else None
                    ),
                    "ioc_english_name": (
                        detection.ioc_english_name
                        if hasattr(detection, "ioc_english_name")
                        else None
                    ),
                    "translated_name": (
                        detection.translated_name if hasattr(detection, "translated_name") else None
                    ),
                    "family": detection.family if hasattr(detection, "family") else None,
                    "genus": detection.genus if hasattr(detection, "genus") else None,
                    "order_name": detection.order_name
                    if hasattr(detection, "order_name")
                    else None,
                }
                for detection in detections
            ]
        else:
            # Use regular detection data (fallback)
            detections = data_manager.get_recent_detections(limit)
            detection_list = [
                {
                    "id": detection.id,
                    "scientific_name": detection.scientific_name,
                    "common_name": detection.common_name,
                    "confidence": detection.confidence,
                    "timestamp": detection.timestamp.isoformat(),
                    "latitude": detection.latitude,
                    "longitude": detection.longitude,
                }
                for detection in detections
            ]
        return JSONResponse({"detections": detection_list, "count": len(detection_list)})
    except Exception as e:
        logger.error("Error getting recent detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving recent detections") from e


@router.get("/count")
@inject
async def get_detection_count(
    target_date: date | None = None,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Get detection count for a specific date (defaults to today)."""
    try:
        if target_date is None:
            target_date = datetime.now(UTC).date()

        # Use DataManager for counting
        counts = data_manager.count_by_date()
        count = counts.get(target_date, 0)

        return JSONResponse({"date": target_date.isoformat(), "count": count})
    except Exception as e:
        logger.error("Error getting detection count: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection count") from e


@router.post("/{detection_id}/location")
@inject
async def update_detection_location(
    detection_id: int,
    location: LocationUpdate,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Update detection location with GPS coordinates."""
    try:
        # Get the detection using DataManager
        detection = data_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Update the location using DataManager
        updated_detection = data_manager.update_detection(
            detection_id, {"latitude": location.latitude, "longitude": location.longitude}
        )

        if updated_detection:
            return JSONResponse(
                {
                    "message": "Location updated successfully",
                    "detection_id": detection_id,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                }
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to update detection location")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating detection location: %s", e)
        raise HTTPException(status_code=500, detail="Error updating detection location") from e


@router.get("/{detection_id}")
@inject
async def get_detection(
    detection_id: UUID | int,
    language_code: str = "en",
    include_l10n: bool = True,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Get a specific detection by ID with optional translation data."""
    try:
        # Convert UUID to int if needed
        id_to_use = int(detection_id) if isinstance(detection_id, UUID) else detection_id

        # Try to get localization-enhanced data first
        if include_l10n:
            try:
                detection_with_l10n = data_manager.get_detection_with_localization(
                    id_to_use, language_code
                )
                if detection_with_l10n:
                    detection_data = {
                        "id": detection_with_l10n.id,
                        "scientific_name": detection_with_l10n.scientific_name,
                        "common_name": data_manager.get_species_display_name(
                            detection_with_l10n,
                            prefer_translation=True,
                            language_code=language_code,
                        ),
                        "confidence": detection_with_l10n.confidence,
                        "timestamp": detection_with_l10n.timestamp.isoformat(),
                        "latitude": detection_with_l10n.detection.latitude,
                        "longitude": detection_with_l10n.detection.longitude,
                        "species_confidence_threshold": (
                            detection_with_l10n.detection.species_confidence_threshold
                        ),
                        "week": detection_with_l10n.detection.week,
                        "sensitivity_setting": detection_with_l10n.detection.sensitivity_setting,
                        "overlap": detection_with_l10n.detection.overlap,
                        "ioc_english_name": detection_with_l10n.ioc_english_name,
                        "translated_name": detection_with_l10n.translated_name,
                        "family": detection_with_l10n.family,
                        "genus": detection_with_l10n.genus,
                        "order_name": detection_with_l10n.order_name,
                    }
                    return JSONResponse(detection_data)
            except Exception as ioc_error:
                logger.warning(
                    "Failed to get localization data for detection %s: %s", detection_id, ioc_error
                )

        # Fallback to regular detection
        detection = data_manager.get_detection_by_id(id_to_use)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        detection_data = {
            "id": detection.id,
            "scientific_name": detection.scientific_name,
            "common_name": detection.common_name,
            "confidence": detection.confidence,
            "timestamp": detection.timestamp.isoformat(),
            "latitude": detection.latitude,
            "longitude": detection.longitude,
            "species_confidence_threshold": detection.species_confidence_threshold,
            "week": detection.week,
            "sensitivity_setting": detection.sensitivity_setting,
            "overlap": detection.overlap,
        }
        return JSONResponse(detection_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting detection: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection") from e


@router.get("/{detection_id}/spectrogram")
@inject
async def get_detection_spectrogram(
    detection_id: int,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    plotting_manager: PlottingManager = Depends(Provide[Container.plotting_manager]),  # noqa: B008
) -> StreamingResponse:
    """Generate and return a spectrogram for a specific detection's audio file."""
    try:
        # Get the detection to find the associated audio file path
        detection = data_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Get the audio file path from the detection
        if not detection.audio_file_path:
            raise HTTPException(
                status_code=404, detail="No audio file associated with this detection"
            )

        spectrogram_buffer = plotting_manager.generate_spectrogram(detection.audio_file_path)
        return StreamingResponse(content=iter([spectrogram_buffer.read()]), media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating spectrogram for detection %s: %s", detection_id, e)
        raise HTTPException(status_code=500, detail=f"Error generating spectrogram: {e}") from e


@router.get("/species/summary")
@inject
async def get_species_summary(
    language_code: str = "en",
    since: datetime | None = None,
    family_filter: str | None = None,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Get detection count summary by species with translation data."""
    try:
        species_summary = data_manager.count_by_species(
            start_date=since,
            include_localized_names=True,
            language_code=language_code,
        )

        # Filter by family if requested
        if family_filter and isinstance(species_summary, list):
            species_summary = [s for s in species_summary if s.get("family") == family_filter]

        return JSONResponse({"species": species_summary, "count": len(species_summary)})
    except Exception as e:
        logger.error("Error getting species summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species summary") from e


@router.get("/families/summary")
@inject
async def get_family_summary(
    language_code: str = "en",
    since: datetime | None = None,
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
) -> JSONResponse:
    """Get detection count summary by taxonomic family with translation data."""
    try:
        # Get species summary with family information
        species_summary = data_manager.count_by_species(
            start_date=since,
            include_localized_names=True,
            language_code=language_code,
        )

        # Aggregate by family
        family_counts: dict[str, int] = {}
        if isinstance(species_summary, list):
            for species in species_summary:
                family = species.get("family", "Unknown")
                if family in family_counts:
                    family_counts[family] += species.get("count", 0)
                else:
                    family_counts[family] = species.get("count", 0)

        family_summary = [
            {"family": family, "count": count}
            for family, count in sorted(family_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        return JSONResponse({"families": family_summary, "count": len(family_summary)})
    except Exception as e:
        logger.error("Error getting family summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving family summary") from e
