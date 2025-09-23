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

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.utils.cache import Cache
from birdnetpi.utils.time_periods import calculate_period_boundaries
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.detections import DetectionEvent, LocationUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

# Track if cache invalidation handler is registered
_paginated_cache_handler_registered = False


def _get_cache_invalidation_handler(cache: Cache) -> Callable:
    """Create a cache invalidation handler with the cache instance."""

    def _invalidate_paginated_cache(sender: object, **kwargs: object) -> None:
        """Invalidate paginated detection cache when new detection arrives."""
        logger.debug("Invalidating paginated detections cache due to new detection")
        # Use Redis pattern-based deletion to clear all paginated detection caches
        try:
            # Delete all keys matching the paginated detections pattern
            deleted = cache.delete_pattern("birdnet_analytics:*paginated*")
            logger.debug(f"Deleted {deleted} paginated detection cache entries")

            # Also delete species analytics caches
            deleted = cache.delete_pattern("birdnet_analytics:*species_analytics*")
            logger.debug(f"Deleted {deleted} species analytics cache entries")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")

    return _invalidate_paginated_cache


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
    """Get recent bird detections with taxa and translation data."""
    try:
        # Always get detections with taxa enrichment
        detections = await detection_query_service.query_detections(
            limit=limit,
            offset=offset,
            order_by="timestamp",
            order_desc=True,
            include_first_detections=True,  # API always provides rich metadata
        )
        detection_list = []
        for detection in detections:
            # Use model_dump with config context - this automatically handles display_name
            # and sets common_name for backward compatibility
            det_dict = detection.model_dump(
                mode="json",
                exclude_none=True,
                exclude={"species_tensor", "audio_file_id", "week", "hour_epoch"},
                context={"config": config},
            )
            detection_list.append(det_dict)
        return JSONResponse({"detections": detection_list, "count": len(detection_list)})
    except Exception as e:
        logger.error("Error getting recent detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving recent detections") from e


@router.get("/")
@inject
async def get_detections(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=10, le=200, description="Items per page"),
    period: str = Query("day", description="Time period filter"),
    search: str | None = Query(None, description="Search species name"),
    sort_by: str = Query(
        "timestamp", description="Field to sort by: timestamp, species, confidence, first"
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    presentation_manager: PresentationManager = Depends(  # noqa: B008
        Provide[Container.presentation_manager]
    ),
    cache: Cache = Depends(  # noqa: B008
        Provide[Container.cache_service]
    ),
) -> JSONResponse:
    """Get paginated detections with filtering.

    This endpoint now delegates to PresentationManager for data processing
    and formatting, keeping the router focused on HTTP concerns.
    """
    # Register cache invalidation handler if not already registered
    global _paginated_cache_handler_registered
    if cache and not _paginated_cache_handler_registered:
        handler = _get_cache_invalidation_handler(cache)
        detection_signal.connect(handler)
        _paginated_cache_handler_registered = True

    try:
        # Generate cache key including all parameters
        search_part = search or "all"
        cache_key = (
            f"paginated_detections_{page}_{per_page}_{period}_{search_part}_{sort_by}_{sort_order}"
        )

        # Check cache first
        if cache:
            cached_response = cache.get("api_paginated", key=cache_key)
            if cached_response is not None:
                logger.debug(f"Returning cached paginated detections: {cache_key}")
                return JSONResponse(cached_response)

        # Delegate to PresentationManager for data processing and formatting
        response_data = await presentation_manager.format_paginated_detections(
            period=period,
            page=page,
            per_page=per_page,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Cache the response data before returning
        if cache:
            cache.set("api_paginated", response_data, key=cache_key, ttl=300)  # 5 minute TTL
            logger.debug(f"Cached paginated detections: {cache_key}")

        return JSONResponse(response_data)
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
    config: BirdNETConfig = Depends(  # noqa: B008
        Provide[Container.config]
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
            # Use model_dump with config context - handles display_name automatically
            det_dict = detection.model_dump(
                mode="json",
                exclude_none=True,
                include={
                    "id",
                    "scientific_name",
                    "common_name",
                    "family",
                    "genus",
                    "confidence",
                    "timestamp",
                    "date",
                    "time",
                },
                context={"config": config},
            )
            # Convert confidence to percentage for this endpoint
            det_dict["confidence"] = round(detection.confidence * 100, 1)
            # Override time format to include seconds for this endpoint
            det_dict["time"] = detection.timestamp.strftime("%H:%M:%S")
            recordings.append(det_dict)

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


@router.get("/summary")
@inject
async def get_detections_summary(
    period: str = Query(
        "day", description="Time period: day, week, month, season, year, historical"
    ),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
) -> JSONResponse:
    """Get detection summary data for period switching.

    This endpoint provides all the data needed to update the all_detections page
    when switching time periods without a full page reload.
    """
    try:
        # Map period to days
        period_map = {
            "day": 1,
            "week": 7,
            "month": 30,
            "season": 90,
            "year": 365,
            "historical": None,
        }

        days = period_map.get(period)
        since = None
        end_time = datetime.now(UTC).replace(tzinfo=None)
        if days:
            since = end_time - timedelta(days=days)
            start_time = since
        else:
            # For historical, use a very old date
            start_time = datetime(2020, 1, 1).replace(tzinfo=None)

        # Get species frequency data for the period
        species_summary = await detection_query_service.get_species_summary(since=since)

        # Format species frequency table data - ALL species for the selected period
        species_frequency = []
        for species in species_summary if species_summary else []:
            count = species.get("detection_count", 0)
            species_frequency.append(
                {
                    "name": species.get("best_common_name")
                    or species.get("ioc_english_name", "Unknown"),
                    "scientific_name": species.get("scientific_name", ""),
                    "count": count,  # Single count for the selected period
                }
            )

        # Get detection count for the period
        total_detections = await detection_query_service.get_detection_count(
            start_time=start_time, end_time=end_time
        )

        # Count unique species
        species_count = len(species_frequency)

        # Simple peak activity calculation (placeholder)
        peak_time = "12:00"
        peak_count = 0

        # Format subtitle
        location = "Location not set"
        current_date_str = datetime.now(UTC).strftime("%B %d, %Y")
        subtitle = f"{location} · {current_date_str} · {species_count} species active"

        # Format statistics HTML
        period_label = period.capitalize()
        statistics = (
            f'{period_label}: <span class="stat-value">{species_count}</span> species, '
            f'<span class="stat-value">{total_detections}</span> detections · '
            f'Peak activity: <span class="stat-value">{peak_time}</span> '
            f"({peak_count} detection{'s' if peak_count != 1 else ''})"
        )

        return JSONResponse(
            {
                "species_frequency": species_frequency,
                "subtitle": subtitle,
                "statistics": statistics,
                "species_count": species_count,
                "total_detections": total_detections,
            }
        )

    except Exception as e:
        logger.error(f"Error getting detection summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get detection summary: {e!s}",
        ) from e


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

    def handler(sender: object, **kwargs: object) -> None:
        """Handle detection signal and put it in the queue."""
        detection: Detection | None = kwargs.get("detection")  # type: ignore[arg-type]
        if detection:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, detection)
                logger.info(f"Queued detection for SSE: {detection.id}")
            except Exception as e:
                logger.error(f"Error queuing detection for SSE: {e}")

    return handler


def _format_detection_event(detection: Detection) -> dict[str, Any]:
    """Format a detection as an SSE event."""
    # Use model_dump for consistent serialization
    det_dict = detection.model_dump(
        mode="json",
        exclude_none=True,
        include={
            "id",
            "timestamp",
            "scientific_name",
            "common_name",
            "confidence",
            "latitude",
            "longitude",
        },
    )
    # Ensure timestamp is treated as UTC by adding Z suffix
    if det_dict.get("timestamp"):
        det_dict["timestamp"] = det_dict["timestamp"] + "Z"
    return det_dict


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
    """Get a specific detection by ID with taxa and translation data."""
    try:
        # Always get detection with taxa enrichment
        if isinstance(detection_id, UUID):
            detection_with_taxa = await detection_query_service.get_detection_with_taxa(
                detection_id
            )
            if detection_with_taxa:
                # Use model_dump with config context for consistent serialization
                # The model serializer handles display_name and sets common_name automatically
                detection_data = detection_with_taxa.model_dump(
                    mode="json",
                    exclude_none=True,
                    include={
                        "id",
                        "scientific_name",
                        "common_name",
                        "confidence",
                        "timestamp",
                        "latitude",
                        "longitude",
                        "species_confidence_threshold",
                        "week",
                        "sensitivity_setting",
                        "overlap",
                        "ioc_english_name",
                        "translated_name",
                        "family",
                        "genus",
                        "order_name",
                    },
                    context={"config": config},
                )
                return JSONResponse(detection_data)

        # Fallback for integer IDs - get basic detection
        id_to_use = int(detection_id) if isinstance(detection_id, UUID) else detection_id
        detection = await data_manager.get_detection_by_id(id_to_use)
        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Use model_dump for consistent serialization with config context
        detection_data = detection.model_dump(
            mode="json",
            exclude_none=True,
            include={
                "id",
                "scientific_name",
                "common_name",
                "confidence",
                "timestamp",
                "latitude",
                "longitude",
                "species_confidence_threshold",
                "week",
                "sensitivity_setting",
                "overlap",
            },
            context={"config": config},
        )
        return JSONResponse(detection_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting detection: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection") from e


@router.get("/species/summary")
@inject
async def get_species_summary(
    period: str | None = Query(
        None, description="Time period (day, week, month, season, year, historical)"
    ),
    since: datetime | None = None,
    family_filter: str | None = Query(None, description="Filter by taxonomic family"),
    detection_query_service: DetectionQueryService = Depends(  # noqa: B008
        Provide[Container.detection_query_service]
    ),
    config: BirdNETConfig = Depends(Provide[Container.config]),  # noqa: B008
    cache: Cache = Depends(Provide[Container.cache_service]),  # noqa: B008
) -> JSONResponse:
    """Get species summary with detection counts and first detection info.

    Can be filtered by period (day/week/month/season/year) or by explicit date range.
    Returns formatted species list with is_first_ever boolean flags.
    """
    try:
        # If period is provided, calculate date range using calendar boundaries
        if period:
            import pytz

            # Get the configured timezone
            user_tz = pytz.timezone(config.timezone) if config.timezone != "UTC" else UTC

            # Get current time in user's timezone
            now_utc = datetime.now(UTC)
            now_local = now_utc.astimezone(user_tz)

            # Use helper function to calculate period boundaries
            # Validate and cast period to PeriodType
            if period in ["day", "week", "month", "season", "year", "historical"]:
                period_to_use = period  # type: ignore[assignment]
            else:
                period_to_use = "day"  # type: ignore[assignment]
            start_local, end_local = calculate_period_boundaries(
                period_to_use, now_local, config.timezone
            )

            # Convert to UTC for database queries (unless historical)
            if period == "historical":
                since = None
                _end_date = None
            else:
                since = start_local.astimezone(UTC)
                _end_date = end_local.astimezone(UTC)

        # Get species summary with first detection info
        species_summary = await detection_query_service.get_species_summary(
            since=since,
            family_filter=family_filter,
            include_first_detections=True,
        )

        # Format species data with is_first_ever boolean
        species_list = []
        for species in species_summary:
            if isinstance(species, dict):
                name = (
                    species.get("translated_name", None)
                    or species.get("best_common_name", None)
                    or species.get("common_name", None)
                    or species.get("scientific_name", "Unknown")
                )
                scientific_name = species.get("scientific_name", "Unknown")
                count = species.get("detection_count", species.get("count", 0))
                first_ever_detection = species.get("first_ever_detection")
            else:
                name = (
                    getattr(species, "translated_name", None)
                    or getattr(species, "best_common_name", None)
                    or getattr(species, "common_name", None)
                    or getattr(species, "scientific_name", "Unknown")
                )
                scientific_name = getattr(species, "scientific_name", "Unknown")
                count = getattr(species, "count", 0)
                first_ever_detection = getattr(species, "first_ever_detection", None)

            # Determine if this is a first ever detection
            is_first_ever = bool(first_ever_detection)

            species_list.append(
                {
                    "name": name,
                    "scientific_name": scientific_name,
                    "detection_count": count,  # Use consistent field name
                    "is_first_ever": is_first_ever,
                    "first_ever_detection": first_ever_detection,
                }
            )

        # Sort by count descending
        species_list.sort(key=lambda x: x["detection_count"], reverse=True)

        # Calculate total detections
        total_detections = sum(s["detection_count"] for s in species_list)

        # Prepare response
        response_data = {
            "species": species_list,
            "count": len(species_list),
            "total_detections": total_detections,
        }

        # Add period info if provided
        if period:
            response_data["period"] = period
            response_data["period_label"] = {
                "day": "Today",
                "week": "This Week",
                "month": "This Month",
                "season": "This Season",
                "year": "This Year",
                "historical": "All Time",
            }.get(period, "This Period")

        return JSONResponse(response_data)
    except Exception as e:
        logger.error("Error getting species summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species summary") from e
