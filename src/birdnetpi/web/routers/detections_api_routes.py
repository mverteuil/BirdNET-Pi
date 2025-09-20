import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

# from birdnetpi.analytics.plotting_manager import PlottingManager  # Removed - analytics refactor
# TODO: Re-implement spectrogram generation without PlottingManager
from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.detections import DetectionEvent, LocationUpdate

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
    """Receive a new detection event and dispatch it.

    DataManager handles both audio file saving and database persistence.
    """
    logger.info(
        f"Received detection: {detection_event.species_tensor or 'Unknown'} "
        f"with confidence {detection_event.confidence}"
    )

    # Create detection - DataManager handles audio saving and database persistence
    # Store the raw data from BirdNET as-is
    # The @emit_detection_event decorator on create_detection handles event emission
    try:
        saved_detection = await data_manager.create_detection(detection_event)
        return {"message": "Detection received and dispatched", "detection_id": saved_detection.id}
    except Exception as e:
        import traceback

        logger.error(f"Failed to create detection: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create detection: {e!s}",
        ) from e


@router.get("/recent")
@inject
async def get_recent_detections(
    limit: int = 10,
    offset: int = 0,  # Added for compatibility with old endpoint
    language_code: str = "en",
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get recent bird detections with taxa and translation data."""
    try:
        # Always get detections with taxa enrichment
        detections = await detection_query_service.query_detections(
            limit=limit,
            offset=offset,
            order_by="timestamp",
            order_desc=True,
            language_code=language_code,
        )
        detection_list = [
            {
                "id": str(detection.id),
                "scientific_name": detection.scientific_name,
                "common_name": detection_query_service.get_species_display_name(
                    detection, True, language_code
                ),
                "confidence": detection.confidence,
                "timestamp": detection.timestamp.isoformat(),
                "latitude": detection.latitude,
                "longitude": detection.longitude,
                "ioc_english_name": detection.ioc_english_name,
                "translated_name": detection.translated_name,
                "family": detection.family,
                "genus": detection.genus,
                "order_name": detection.order_name,
            }
            for detection in detections
        ]
        return JSONResponse({"detections": detection_list, "count": len(detection_list)})
    except Exception as e:
        logger.error("Error getting recent detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving recent detections") from e


@router.get("/paginated")
@inject
async def get_paginated_detections(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=10, le=200, description="Items per page"),
    period: str = Query("day", description="Time period filter"),
    search: str | None = Query(None, description="Search species name"),
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
    config: BirdNETConfig = Depends(  # noqa: B008
        Provide[Container.config]
    ),
) -> JSONResponse:
    """Get paginated detections with filtering."""
    try:
        # Calculate date range based on period
        end_time = datetime.now()
        period_days = {
            "day": 1,
            "week": 7,
            "month": 30,
            "season": 90,
            "year": 365,
            "historical": 36500,  # ~100 years
        }
        days = period_days.get(period, 1)
        start_time = end_time - timedelta(days=days)

        # Get detections with taxa enrichment for proper display names
        all_detections = await detection_query_service.query_detections(
            start_date=start_time,
            end_date=end_time,
            language_code=config.language,
            order_by="timestamp",
            order_desc=True,
        )

        # Filter by search term if provided
        if search:
            search_lower = search.lower()
            all_detections = [
                d
                for d in all_detections
                if search_lower in (d.common_name or "").lower()
                or search_lower in (d.scientific_name or "").lower()
            ]

        # Sort by timestamp descending (convert to list for sorting)
        all_detections = sorted(all_detections, key=lambda d: d.timestamp, reverse=True)

        # Calculate pagination
        total = len(all_detections)
        total_pages = (total + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Get page of detections
        page_detections = all_detections[offset : offset + per_page]

        # Format response using proper display names
        detection_list = []
        for detection in page_detections:
            # Always use the display name logic which handles localization properly
            display_name = detection_query_service.get_species_display_name(
                detection, True, config.language
            )

            detection_list.append(
                {
                    "id": str(detection.id),
                    "timestamp": detection.timestamp.strftime("%H:%M"),
                    "date": detection.timestamp.strftime("%Y-%m-%d"),
                    "species": display_name,
                    "scientific_name": detection.scientific_name,
                    "confidence": round(detection.confidence, 2),
                }
            )

        return JSONResponse(
            {
                "detections": detection_list,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            }
        )
    except Exception as e:
        logger.error("Error getting paginated detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detections") from e


@router.get("/count")
@inject
async def get_detection_count(
    target_date: date | None = None,
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get detection count for a specific date (defaults to today)."""
    try:
        if target_date is None:
            target_date = datetime.now(UTC).date()

        # Use DetectionQueryService for counting
        counts = await detection_query_service.count_by_date()
        count = counts.get(target_date, 0)

        return JSONResponse({"date": target_date.isoformat(), "count": count})
    except Exception as e:
        logger.error("Error getting detection count: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection count") from e


@router.get("/best-recordings")
@inject
async def get_best_recordings(
    family: str | None = Query(None, description="Filter by taxonomic family"),
    genus: str | None = Query(None, description="Filter by genus"),
    species: str | None = Query(None, description="Filter by species scientific name"),
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of recordings to return"),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get best recordings with optional taxonomic filtering.

    This endpoint supports hierarchical filtering:
    - Filter by family to get best recordings for all species in that family
    - Filter by genus to get best recordings for all species in that genus
    - Filter by species to get best recordings for a specific species
    """
    try:
        # Build filters for query
        filters = {}

        # Apply taxonomic filters - most specific takes precedence
        if species:
            filters["species"] = species
        elif genus:
            filters["genus"] = genus
        elif family:
            filters["family"] = family

        # Query detections with filters
        detections = await detection_query_service.query_detections(
            min_confidence=min_confidence,
            limit=limit,
            order_by="confidence",
            order_desc=True,
            **filters,
        )

        # Format response
        recordings = []
        for detection in detections:
            recordings.append(
                {
                    "id": str(detection.id),
                    "scientific_name": detection.scientific_name,
                    "common_name": detection.common_name or detection.ioc_english_name,
                    "family": detection.family,
                    "genus": detection.genus,
                    "confidence": round(detection.confidence * 100, 1),
                    "timestamp": detection.timestamp.isoformat(),
                    "date": detection.timestamp.strftime("%Y-%m-%d"),
                    "time": detection.timestamp.strftime("%H:%M:%S"),
                }
            )

        # Calculate summary stats
        if recordings:
            avg_confidence = sum(r["confidence"] for r in recordings) / len(recordings)
            dates = [d.timestamp for d in detections]
            date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
            unique_species = len({r["scientific_name"] for r in recordings})
        else:
            avg_confidence = 0
            date_range = "No recordings"
            unique_species = 0

        return JSONResponse(
            {
                "recordings": recordings,
                "count": len(recordings),
                "avg_confidence": round(avg_confidence, 1),
                "date_range": date_range,
                "unique_species": unique_species,
                "filters": {
                    "family": family,
                    "genus": genus,
                    "species": species,
                    "min_confidence": min_confidence,
                },
            }
        )
    except Exception as e:
        logger.error("Error getting best recordings: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving best recordings") from e


@router.get("/taxonomy/families")
@inject
async def get_taxonomy_families(
    has_detections: bool = Query(True, description="Only return families with detections"),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get list of all taxonomic families, optionally filtered to those with detections."""
    try:
        if has_detections:
            # Get families from actual detections
            species_summary = await detection_query_service.get_species_summary()
            families = set()
            if isinstance(species_summary, list):
                for species in species_summary:
                    if family := species.get("family"):
                        families.add(family)
            family_list = sorted(families)
        else:
            # Would need to query IOC database for all families
            # For now, just return families with detections
            species_summary = await detection_query_service.get_species_summary()
            families = set()
            if isinstance(species_summary, list):
                for species in species_summary:
                    if family := species.get("family"):
                        families.add(family)
            family_list = sorted(families)

        return JSONResponse({"families": family_list, "count": len(family_list)})
    except Exception as e:
        logger.error("Error getting families: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving families") from e


@router.get("/taxonomy/genera")
@inject
async def get_taxonomy_genera(
    family: str = Query(..., description="Family to get genera for"),
    has_detections: bool = Query(True, description="Only return genera with detections"),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get list of genera within a family, optionally filtered to those with detections."""
    try:
        if has_detections:
            # Get genera from actual detections in this family
            species_summary = await detection_query_service.get_species_summary()
            genera = set()
            if isinstance(species_summary, list):
                for species in species_summary:
                    if species.get("family") == family and (genus := species.get("genus")):
                        genera.add(genus)
            genus_list = sorted(genera)
        else:
            # Would need to query IOC database for all genera in family
            # For now, just return genera with detections
            species_summary = await detection_query_service.get_species_summary()
            genera = set()
            if isinstance(species_summary, list):
                for species in species_summary:
                    if species.get("family") == family and (genus := species.get("genus")):
                        genera.add(genus)
            genus_list = sorted(genera)

        return JSONResponse({"genera": genus_list, "family": family, "count": len(genus_list)})
    except Exception as e:
        logger.error("Error getting genera: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving genera") from e


@router.get("/taxonomy/species")
@inject
async def get_taxonomy_species(
    genus: str = Query(..., description="Genus to get species for"),
    family: str | None = Query(None, description="Optional family filter"),
    has_detections: bool = Query(True, description="Only return species with detections"),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get list of species within a genus, optionally filtered to those with detections."""
    try:
        # For now, always get species from actual detections
        # TODO: Query IOC database directly when has_detections=False
        species_summary = await detection_query_service.get_species_summary()
        species_list = []

        # Debug logging
        species_count = len(species_summary) if species_summary else 0
        logger.info(f"Species summary for genus {genus}: {species_count} total species")

        if isinstance(species_summary, list):
            for species in species_summary:
                if species.get("genus") == genus:
                    if not family or species.get("family") == family:
                        # Debug: log the species data
                        if species.get("scientific_name") == "Cyanocitta cristata":
                            logger.info(f"Found Cyanocitta cristata data: {species}")
                        species_list.append(
                            {
                                "scientific_name": species.get("scientific_name"),
                                "common_name": species.get("best_common_name")
                                or species.get("ioc_english_name"),
                                "count": species.get("detection_count", 0),
                            }
                        )

        # Sort by count descending
        species_list.sort(key=lambda x: x["count"], reverse=True)

        return JSONResponse(
            {"species": species_list, "genus": genus, "family": family, "count": len(species_list)}
        )
    except Exception as e:
        logger.error("Error getting species: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species") from e


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
        detection = await data_manager.get_detection_by_id(detection_id)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Update the location using DataManager
        updated_detection = await data_manager.update_detection(
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


def _create_detection_handler(
    loop: asyncio.AbstractEventLoop, queue: asyncio.Queue
) -> Callable[..., None]:
    """Create a handler for detection signals."""

    def handler(sender: object, **kwargs: Any) -> None:  # noqa: ANN401
        """Handle detection signal and put it in the queue."""
        detection: Detection | None = kwargs.get("detection")
        if detection:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, detection)
                logger.info(f"Queued detection for SSE: {detection.id}")
            except Exception as e:
                logger.error(f"Error queuing detection for SSE: {e}")

    return handler


def _format_detection_event(detection: Detection) -> dict[str, Any]:
    """Format a detection as an SSE event."""
    timestamp_str = ""
    if detection.timestamp:
        # Ensure timestamp is treated as UTC by adding Z suffix
        timestamp_str = detection.timestamp.isoformat() + "Z"

    return {
        "id": str(detection.id),
        "timestamp": timestamp_str,
        "scientific_name": detection.scientific_name,
        "common_name": detection.common_name,
        "confidence": detection.confidence,
        "latitude": detection.latitude,
        "longitude": detection.longitude,
    }


@router.get("/stream")
@inject
async def stream_detections(
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> StreamingResponse:
    """Stream new detections using Server-Sent Events (SSE).

    This endpoint streams real-time detection events as they occur.
    Clients can use EventSource API to receive updates.
    """

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events from detection signals."""
        # Create a queue to receive detection events
        detection_queue: asyncio.Queue = asyncio.Queue()

        # Create and connect the detection handler
        loop = asyncio.get_running_loop()
        detection_handler = _create_detection_handler(loop, detection_queue)
        detection_signal.connect(detection_handler, weak=False)
        logger.info("SSE handler connected to detection signal")

        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            # Stream detection events
            while True:
                try:
                    # Wait for new detection with timeout to keep connection alive
                    detection = await asyncio.wait_for(detection_queue.get(), timeout=30.0)
                    logger.info(f"Got detection from queue for SSE: {detection.id}")

                    # Format and send detection event
                    event_data = _format_detection_event(detection)
                    logger.info(f"Sending detection event via SSE: {detection.scientific_name}")
                    yield f"event: detection\ndata: {json.dumps(event_data, default=str)}\n\n"

                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    heartbeat_data = {"timestamp": datetime.now().isoformat()}
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"

                except Exception as e:
                    logger.error(f"Error processing detection for SSE: {e}")
                    # Continue streaming despite errors

        except asyncio.CancelledError:
            # Clean disconnection
            pass
        except Exception as e:
            logger.error(f"Error in detection streaming: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Disconnect from signal when done
            detection_signal.disconnect(detection_handler)
            logger.info("SSE handler disconnected from detection signal")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@router.get("/{detection_id}")
@inject
async def get_detection(
    detection_id: UUID | int,
    language_code: str = "en",
    data_manager: DataManager = Depends(  # noqa: B008
        Provide[Container.data_manager]
    ),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get a specific detection by ID with taxa and translation data."""
    try:
        # Always get detection with taxa enrichment
        if isinstance(detection_id, UUID):
            detection_with_taxa = await detection_query_service.get_detection_with_taxa(
                detection_id,
                language_code,
            )
            if detection_with_taxa:
                detection_data = {
                    "id": str(detection_with_taxa.id),
                    "scientific_name": detection_with_taxa.scientific_name,
                    "common_name": detection_query_service.get_species_display_name(
                        detection_with_taxa,
                        prefer_translation=True,
                        language_code=language_code,
                    ),
                    "confidence": detection_with_taxa.confidence,
                    "timestamp": detection_with_taxa.timestamp.isoformat(),
                    "latitude": detection_with_taxa.latitude,
                    "longitude": detection_with_taxa.longitude,
                    "species_confidence_threshold": (
                        detection_with_taxa.species_confidence_threshold
                    ),
                    "week": detection_with_taxa.week,
                    "sensitivity_setting": detection_with_taxa.sensitivity_setting,
                    "overlap": detection_with_taxa.overlap,
                    "ioc_english_name": detection_with_taxa.ioc_english_name,
                    "translated_name": detection_with_taxa.translated_name,
                    "family": detection_with_taxa.family,
                    "genus": detection_with_taxa.genus,
                    "order_name": detection_with_taxa.order_name,
                }
                return JSONResponse(detection_data)

        # Fallback for integer IDs - get basic detection
        id_to_use = int(detection_id) if isinstance(detection_id, UUID) else detection_id
        detection = await data_manager.get_detection_by_id(id_to_use)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        detection_data = {
            "id": str(detection.id),
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


# TODO: Re-implement spectrogram generation endpoint
# The spectrogram endpoint has been temporarily disabled after removing PlottingManager.
# This functionality needs to be re-implemented using a different approach.
# @router.get("/{detection_id}/spectrogram")
# @inject
# async def get_detection_spectrogram(
#     detection_id: int,
#     data_manager: DataManager = Depends(
#         Provide[Container.data_manager]
#     ),
# ) -> StreamingResponse:
#     """Generate and return a spectrogram for a specific detection's audio file."""
#     # Implementation temporarily removed - needs replacement for PlottingManager
#     raise HTTPException(
#         status_code=501,
#         detail="Spectrogram generation temporarily unavailable - being reimplemented"
#     )


@router.get("/species/frequency")
@inject
async def get_species_frequency(
    hours: int = Query(24, description="Hours to look back"),
    analytics_manager: AnalyticsManager = Depends(  # noqa: B008
        Provide[Container.analytics_manager]
    ),
) -> JSONResponse:
    """Get species detection frequency for the specified time period."""
    try:
        frequency = await analytics_manager.get_species_frequency_analysis(hours=hours)
        return JSONResponse({"species": frequency, "hours": hours})
    except Exception as e:
        logger.error("Error getting species frequency: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species frequency") from e


@router.get("/species/summary")
@inject
async def get_species_summary(
    language_code: str = "en",
    since: datetime | None = None,
    family_filter: str | None = None,
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get detection count summary by species with translation data."""
    try:
        # Use get_species_summary which returns list of dicts with localized names
        species_summary = await detection_query_service.get_species_summary(
            language_code=language_code,
            since=since,
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
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get detection count summary by taxonomic family with translation data."""
    try:
        # Get species summary with family information
        species_summary = await detection_query_service.get_species_summary(
            language_code=language_code,
            since=since,
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
