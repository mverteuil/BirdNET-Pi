import asyncio
import json
import logging
import traceback
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import h3
import pytz
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse

from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.detections.cleanup import DetectionCleanupService
from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.cache import Cache
from birdnetpi.utils.time_periods import calculate_period_boundaries
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.admin import (
    EBirdCleanupPreviewRequest,
    EBirdCleanupRequest,
    EBirdCleanupResponse,
)
from birdnetpi.web.models.detections import (
    BestRecordingsFilters,
    BestRecordingsResponse,
    DetectionCountResponse,
    DetectionCreatedResponse,
    DetectionDetailResponse,
    DetectionEvent,
    DetectionResponse,
    DetectionsSummaryResponse,
    LocationUpdate,
    LocationUpdateResponse,
    PaginatedDetectionsResponse,
    PaginationInfo,
    RecentDetectionsResponse,
    SpeciesChecklistItem,
    SpeciesChecklistResponse,
    SpeciesFrequency,
    SpeciesInfo,
    SpeciesSummaryResponse,
    TaxonomyFamiliesResponse,
    TaxonomyGeneraResponse,
    TaxonomySpeciesItem,
    TaxonomySpeciesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/detections")

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
            logger.debug("Deleted %d paginated detection cache entries", deleted)

            # Also delete species analytics caches
            deleted = cache.delete_pattern("birdnet_analytics:*species_analytics*")
            logger.debug("Deleted %d species analytics cache entries", deleted)
        except Exception as e:
            logger.warning("Failed to invalidate cache: %s", e)

    return _invalidate_paginated_cache


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=DetectionCreatedResponse)
@inject
async def create_detection(
    data_manager: Annotated[DataManager, Depends(Provide[Container.data_manager])],
    core_database: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    ebird_service: Annotated[EBirdRegionService, Depends(Provide[Container.ebird_region_service])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    detection_event: DetectionEvent,
) -> DetectionCreatedResponse:
    """Receive a new detection event and dispatch it.

    DataManager handles both audio file saving and database persistence.
    eBird filtering can optionally filter or warn about detections based on regional confidence.
    """
    logger.info(
        "Received detection: %s with confidence %s",
        detection_event.species_tensor or "Unknown",
        detection_event.confidence,
    )

    # Apply eBird filtering if enabled (detection-time filtering)
    if (
        config.ebird_filtering.enabled
        and config.ebird_filtering.detection_mode != "off"
        and detection_event.latitude is not None
        and detection_event.longitude is not None
    ):
        try:
            should_filter, reason = await _apply_ebird_filter(
                core_database=core_database,
                ebird_service=ebird_service,
                config=config,
                scientific_name=detection_event.scientific_name,
                latitude=detection_event.latitude,
                longitude=detection_event.longitude,
            )

            if should_filter:
                if config.ebird_filtering.detection_mode == "warn":
                    # Warn mode: Log but allow detection
                    logger.warning(
                        "eBird filter would block %s: %s",
                        detection_event.species_tensor,
                        reason,
                    )
                elif config.ebird_filtering.detection_mode == "filter":
                    # Filter mode: Block detection
                    logger.info(
                        "eBird filter blocked %s: %s",
                        detection_event.species_tensor,
                        reason,
                    )
                    return DetectionCreatedResponse(
                        message=f"Detection filtered: {reason}",
                        detection_id=None,
                    )
        except Exception as e:
            # Don't fail detection creation if eBird filtering fails
            logger.error("eBird filtering error (allowing detection): %s", e)

    # Create detection - DataManager handles audio saving and database persistence
    # Store the raw data from BirdNET as-is
    # The @emit_detection_event decorator on create_detection handles event emission
    try:
        saved_detection = await data_manager.create_detection(detection_event)
        return DetectionCreatedResponse(
            message="Detection received and dispatched", detection_id=saved_detection.id
        )
    except Exception as e:
        logger.error("Failed to create detection: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create detection: {e!s}",
        ) from e


def _check_strictness(confidence_tier: str, strictness: str) -> tuple[bool, str]:
    """Check if a species should be blocked based on strictness level.

    Args:
        confidence_tier: Species confidence tier (vagrant, rare, uncommon, common)
        strictness: Strictness level setting

    Returns:
        Tuple of (should_block, reason)
    """
    if strictness == "vagrant" and confidence_tier == "vagrant":
        return (True, f"Species is vagrant in this region (strictness={strictness})")
    elif strictness == "rare" and confidence_tier in ["vagrant", "rare"]:
        return (True, f"Species is {confidence_tier} in this region (strictness={strictness})")
    elif strictness == "uncommon" and confidence_tier in ["vagrant", "rare", "uncommon"]:
        return (True, f"Species is {confidence_tier} in this region (strictness={strictness})")
    elif strictness == "common" and confidence_tier != "common":
        return (
            True,
            f"Species is {confidence_tier}, not common in region (strictness={strictness})",
        )
    return (False, "")


async def _apply_ebird_filter(
    core_database: CoreDatabaseService,
    ebird_service: EBirdRegionService,
    config: BirdNETConfig,
    scientific_name: str,
    latitude: float,
    longitude: float,
) -> tuple[bool, str]:
    """Apply eBird regional confidence filtering to a detection.

    Args:
        core_database: CoreDatabaseService instance for session management
        ebird_service: EBirdRegionService instance
        config: BirdNET configuration
        scientific_name: Scientific name of the species
        latitude: Detection latitude
        longitude: Detection longitude

    Returns:
        Tuple of (should_filter: bool, reason: str)
        - should_filter: True if detection should be blocked
        - reason: Human-readable reason for filtering decision
    """
    # Convert lat/lon to H3 cell at configured resolution
    h3_cell = h3.latlng_to_cell(latitude, longitude, config.ebird_filtering.h3_resolution)

    # Get or create database session and attach eBird pack
    async with core_database.get_async_db() as session:
        try:
            # Attach eBird pack database
            await ebird_service.attach_to_session(session, config.ebird_filtering.region_pack)

            # Query confidence tier for this species at this location
            confidence_tier = await ebird_service.get_species_confidence_tier(
                session, scientific_name, h3_cell
            )

            # Handle unknown species
            if confidence_tier is None:
                behavior = config.ebird_filtering.unknown_species_behavior
                if behavior == "block":
                    return (
                        True,
                        f"Species not found in eBird data for region (behavior={behavior})",
                    )
                else:  # allow
                    return (False, f"Species not in eBird data, allowing (behavior={behavior})")

            # Apply strictness filtering
            strictness = config.ebird_filtering.detection_strictness
            should_block, reason = _check_strictness(confidence_tier, strictness)
            if should_block:
                return (True, reason)

            # Species passes filtering
            return (False, f"Species is {confidence_tier} in this region, allowed")

        finally:
            # Detach eBird database
            try:
                await ebird_service.detach_from_session(session)
            except Exception as e:
                logger.warning("Failed to detach eBird database: %s", e)


@router.get("/recent", response_model=RecentDetectionsResponse)
@inject
async def get_recent_detections(
    # Added for compatibility with old endpoint
    data_manager: Annotated[DataManager, Depends(Provide[Container.data_manager])],
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    limit: int = Query(10, ge=1, le=1000, description="Maximum number of detections to return"),
    offset: int = Query(0, ge=0, description="Number of detections to skip"),
) -> RecentDetectionsResponse:
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
            detection_list.append(
                DetectionResponse(
                    id=detection.id,
                    scientific_name=detection.scientific_name,
                    common_name=detection.common_name or detection.scientific_name,
                    confidence=detection.confidence,
                    timestamp=detection.timestamp,
                    date=detection.date,
                    time=detection.time,
                    latitude=detection.latitude,
                    longitude=detection.longitude,
                    family=detection.family,
                    genus=detection.genus,
                    order_name=detection.order_name,
                    audio_file_id=detection.audio_file_id,
                )
            )
        return RecentDetectionsResponse(detections=detection_list, count=len(detection_list))
    except Exception as e:
        logger.error("Error getting recent detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving recent detections") from e


@router.get("/", response_model=PaginatedDetectionsResponse)
@inject
async def get_detections(
    presentation_manager: Annotated[
        PresentationManager, Depends(Provide[Container.presentation_manager])
    ],
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=10, le=200, description="Items per page"),
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    family: str | None = Query(None, description="Filter by taxonomic family"),
    genus: str | None = Query(None, description="Filter by genus"),
    species: str | None = Query(None, description="Filter by species"),
    search: str | None = Query(None, description="Search species name"),
    sort_by: str = Query(
        "timestamp", description="Field to sort by: timestamp, species, confidence, first"
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
) -> PaginatedDetectionsResponse:
    """Get paginated detections with filtering.

    This endpoint now delegates to PresentationManager for data processing
    and formatting, keeping the router focused on HTTP concerns.

    If start_date and end_date are not provided, defaults to today.
    """
    # Register cache invalidation handler if not already registered
    global _paginated_cache_handler_registered
    if cache and not _paginated_cache_handler_registered:
        handler = _get_cache_invalidation_handler(cache)
        detection_signal.connect(handler)
        _paginated_cache_handler_registered = True

    try:
        # Default to today if dates not provided
        if start_date is None or end_date is None:
            today = datetime.now(UTC).date()
            start_date = start_date or today.isoformat()
            end_date = end_date or today.isoformat()

        # Generate cache key including all parameters
        search_part = search or "all"
        family_part = family or "all"
        genus_part = genus or "all"
        species_part = species or "all"
        cache_key = (
            f"paginated_detections_{page}_{per_page}_{start_date}_{end_date}_"
            f"{family_part}_{genus_part}_{species_part}_{search_part}_{sort_by}_{sort_order}"
        )

        # Check cache first
        if cache:
            cached_response = cache.get("api_paginated", key=cache_key)
            if cached_response is not None:
                logger.debug("Returning cached paginated detections: %s", cache_key)
                return PaginatedDetectionsResponse(**cached_response)

        # Delegate to PresentationManager for data processing and formatting
        response_data = await presentation_manager.format_paginated_detections(
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
            family=family,
            genus=genus,
            species=species,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Cache the response data before returning
        if cache:
            cache.set("api_paginated", response_data, key=cache_key, ttl=300)  # 5 minute TTL
            logger.debug("Cached paginated detections: %s", cache_key)

        return PaginatedDetectionsResponse(**response_data)
    except Exception as e:
        logger.error("Error getting paginated detections: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detections") from e


@router.get("/count", response_model=DetectionCountResponse)
@inject
async def get_detection_count(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    target_date: date | None = None,
) -> DetectionCountResponse:
    """Get detection count for a specific date (defaults to today)."""
    try:
        if target_date is None:
            target_date = datetime.now(UTC).date()

        # Use DetectionQueryService for counting
        counts = await detection_query_service.count_by_date()
        # SQLite's date() returns strings like "2025-01-01", so convert target_date to match
        date_key = target_date.isoformat()
        count = counts.get(date_key, 0)

        return DetectionCountResponse(date=date_key, count=count)
    except Exception as e:
        logger.error("Error getting detection count: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection count") from e


@router.get("/best-recordings", response_model=BestRecordingsResponse)
@inject
async def get_best_recordings(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=10, le=200, description="Items per page"),
    family: str | None = Query(None, description="Filter by taxonomic family"),
    genus: str | None = Query(None, description="Filter by genus"),
    species: str | None = Query(None, description="Filter by species scientific name"),
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold"),
) -> BestRecordingsResponse:
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
        # When filtering by specific species, don't limit per species (show all)
        # Otherwise, limit to 5 per species for diversity
        per_species_limit = None if species else 5

        detections, total_count = await detection_query_service.query_best_recordings_per_species(
            per_species_limit=per_species_limit,
            min_confidence=min_confidence,
            page=page,
            per_page=per_page,
            family=family,
            genus=genus,
            species=species,
        )

        # Calculate pagination metadata
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0
        has_prev = page > 1
        has_next = page < total_pages

        # Format response
        recordings = []
        for detection in detections:
            recordings.append(
                DetectionResponse(
                    id=detection.id,
                    scientific_name=detection.scientific_name,
                    common_name=detection.common_name or detection.scientific_name,
                    confidence=detection.confidence,
                    timestamp=detection.timestamp,
                    date=detection.date,
                    time=detection.timestamp.strftime("%H:%M:%S"),
                    latitude=detection.latitude,
                    longitude=detection.longitude,
                    family=detection.family,
                    genus=detection.genus,
                    order_name=detection.order_name,
                    audio_file_id=detection.audio_file_id,
                )
            )

        # Calculate summary stats
        if recordings:
            avg_confidence = sum(r.confidence for r in recordings) / len(recordings)
            dates = [d.timestamp for d in detections]
            date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
            unique_species = len({r.scientific_name for r in recordings})
        else:
            avg_confidence = 0.0
            date_range = "No recordings"
            unique_species = 0

        return BestRecordingsResponse(
            recordings=recordings,
            count=len(recordings),
            pagination=PaginationInfo(
                page=page,
                per_page=per_page,
                total=total_count,
                total_pages=total_pages,
                has_prev=has_prev,
                has_next=has_next,
            ),
            avg_confidence=round(avg_confidence, 1),
            date_range=date_range,
            unique_species=unique_species,
            filters=BestRecordingsFilters(
                family=family, genus=genus, species=species, min_confidence=min_confidence
            ),
        )
    except Exception as e:
        logger.error("Error getting best recordings: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving best recordings") from e


@router.get("/taxonomy/families", response_model=TaxonomyFamiliesResponse)
@inject
async def get_taxonomy_families(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    has_detections: bool = Query(True, description="Only return families with detections"),
) -> TaxonomyFamiliesResponse:
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

        return TaxonomyFamiliesResponse(families=family_list, count=len(family_list))
    except Exception as e:
        logger.error("Error getting families: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving families") from e


@router.get("/taxonomy/genera", response_model=TaxonomyGeneraResponse)
@inject
async def get_taxonomy_genera(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    family: str = Query(..., description="Family to get genera for"),
    has_detections: bool = Query(True, description="Only return genera with detections"),
) -> TaxonomyGeneraResponse:
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

        return TaxonomyGeneraResponse(genera=genus_list, family=family, count=len(genus_list))
    except Exception as e:
        logger.error("Error getting genera: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving genera") from e


@router.get("/taxonomy/species", response_model=TaxonomySpeciesResponse)
@inject
async def get_taxonomy_species(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    genus: str = Query(..., description="Genus to get species for"),
    family: str | None = Query(None, description="Optional family filter"),
    has_detections: bool = Query(True, description="Only return species with detections"),
) -> TaxonomySpeciesResponse:
    """Get list of species within a genus, optionally filtered to those with detections."""
    try:
        # For now, always get species from actual detections
        # TODO: Query IOC database directly when has_detections=False
        species_summary = await detection_query_service.get_species_summary()
        species_list = []

        # Debug logging
        species_count = len(species_summary) if species_summary else 0
        logger.info("Species summary for genus %s: %d total species", genus, species_count)

        if isinstance(species_summary, list):
            for species in species_summary:
                if species.get("genus") == genus:
                    if not family or species.get("family") == family:
                        # Debug: log the species data
                        if species.get("scientific_name") == "Cyanocitta cristata":
                            logger.info("Found Cyanocitta cristata data: %s", species)
                        species_list.append(
                            TaxonomySpeciesItem(
                                scientific_name=species.get("scientific_name", ""),
                                common_name=species.get("best_common_name")
                                or species.get("ioc_english_name")
                                or "",
                                count=species.get("detection_count", 0),
                            )
                        )

        # Sort by count descending
        species_list.sort(key=lambda x: x.count, reverse=True)

        return TaxonomySpeciesResponse(
            species=species_list, genus=genus, family=family, count=len(species_list)
        )
    except Exception as e:
        logger.error("Error getting species: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species") from e


@router.get("/summary", response_model=DetectionsSummaryResponse)
@inject
async def get_detections_summary(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    period: str = Query(
        "day", description="Time period: day, week, month, season, year, historical"
    ),
) -> DetectionsSummaryResponse:
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

        # Get detection count for the period
        total_detections = await detection_query_service.get_detection_count(
            start_time=start_time, end_time=end_time
        )

        # Format species frequency table data - ALL species for the selected period
        species_frequency = []
        for species in species_summary if species_summary else []:
            count = species.get("detection_count", 0)
            percentage = (count / total_detections * 100) if total_detections > 0 else 0.0
            species_frequency.append(
                SpeciesFrequency(
                    species=species.get("best_common_name")
                    or species.get("ioc_english_name", "Unknown"),
                    count=count,
                    percentage=round(percentage, 1),
                )
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

        return DetectionsSummaryResponse(
            species_frequency=species_frequency,
            subtitle=subtitle,
            statistics=statistics,
            species_count=species_count,
            total_detections=total_detections,
        )

    except Exception as e:
        logger.error("Error getting detection summary: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get detection summary: {e!s}",
        ) from e


@router.post("/{detection_id}/location", response_model=LocationUpdateResponse)
@inject
async def update_detection_location(
    data_manager: Annotated[DataManager, Depends(Provide[Container.data_manager])],
    detection_id: UUID,
    location: LocationUpdate,
) -> LocationUpdateResponse:
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
            return LocationUpdateResponse(
                message="Location updated successfully",
                detection_id=str(detection_id),
                latitude=location.latitude,
                longitude=location.longitude,
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
                logger.info("Queued detection for SSE: %s", detection.id)
            except Exception as e:
                logger.error("Error queuing detection for SSE: %s", e)

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
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
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
                    logger.info("Got detection from queue for SSE: %s", detection.id)

                    # Format and send detection event
                    event_data = _format_detection_event(detection)
                    logger.info("Sending detection event via SSE: %s", detection.scientific_name)
                    yield f"event: detection\ndata: {json.dumps(event_data, default=str)}\n\n"

                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    heartbeat_data = {"timestamp": datetime.now().isoformat()}
                    yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"

                except Exception as e:
                    logger.error("Error processing detection for SSE: %s", e)
                    # Continue streaming despite errors

        except asyncio.CancelledError:
            # Clean disconnection
            pass
        except Exception as e:
            logger.error("Error in detection streaming: %s", e)
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


@router.get("/{detection_id}", response_model=DetectionDetailResponse)
@inject
async def get_detection(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    detection_id: UUID,
) -> DetectionDetailResponse:
    """Get a specific detection by ID with taxa and translation data."""
    try:
        # Get detection with taxa enrichment
        detection_with_taxa = await detection_query_service.get_detection_with_taxa(detection_id)
        if not detection_with_taxa:
            raise HTTPException(status_code=404, detail="Detection not found")

        return DetectionDetailResponse(
            id=detection_with_taxa.id,
            scientific_name=detection_with_taxa.scientific_name,
            common_name=detection_with_taxa.common_name or detection_with_taxa.scientific_name,
            confidence=detection_with_taxa.confidence,
            timestamp=detection_with_taxa.timestamp,
            latitude=detection_with_taxa.latitude,
            longitude=detection_with_taxa.longitude,
            species_confidence_threshold=detection_with_taxa.species_confidence_threshold,
            week=detection_with_taxa.week,
            sensitivity_setting=detection_with_taxa.sensitivity_setting,
            overlap=detection_with_taxa.overlap,
            ioc_english_name=getattr(detection_with_taxa, "ioc_english_name", None),
            translated_name=getattr(detection_with_taxa, "translated_name", None),
            family=getattr(detection_with_taxa, "family", None),
            genus=getattr(detection_with_taxa, "genus", None),
            order_name=getattr(detection_with_taxa, "order_name", None),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting detection: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving detection") from e


@router.get("/species/summary", response_model=SpeciesSummaryResponse)
@inject
async def get_species_summary(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
    period: str | None = Query(
        None, description="Time period (day, week, month, season, year, historical)"
    ),
    since: datetime | None = None,
    family_filter: str | None = Query(None, description="Filter by taxonomic family"),
) -> SpeciesSummaryResponse:
    """Get species summary with detection counts and first detection info.

    Can be filtered by period (day/week/month/season/year) or by explicit date range.
    Returns formatted species list with is_first_ever boolean flags.
    """
    try:
        # If period is provided, calculate date range using calendar boundaries
        if period:
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

            # Get taxonomy fields from the species data
            family = None
            genus = None
            order = None

            if isinstance(species, dict):
                family = species.get("family")
                genus = species.get("genus")
                order = species.get("order_name")
            else:
                family = getattr(species, "family", None)
                genus = getattr(species, "genus", None)
                order = getattr(species, "order_name", None)

            species_list.append(
                SpeciesInfo(
                    name=name,
                    scientific_name=scientific_name,
                    detection_count=count,
                    is_first_ever=is_first_ever,
                    first_ever_detection=first_ever_detection,
                    family=family,
                    genus=genus,
                    order=order,
                )
            )

        # Sort by count descending
        species_list.sort(key=lambda x: x.detection_count, reverse=True)

        # Calculate total detections
        total_detections = sum(s.detection_count for s in species_list)

        # Determine period label if provided
        period_label = None
        if period:
            period_label = {
                "day": "Today",
                "week": "This Week",
                "month": "This Month",
                "season": "This Season",
                "year": "This Year",
                "historical": "All Time",
            }.get(period, "This Period")

        return SpeciesSummaryResponse(
            species=species_list,
            count=len(species_list),
            total_detections=total_detections,
            period=period,
            period_label=period_label,
        )
    except Exception as e:
        logger.error("Error getting species summary: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species summary") from e


@router.get("/species/checklist", response_model=SpeciesChecklistResponse)
@inject
async def get_species_checklist(
    detection_query_service: Annotated[
        DetectionQueryService, Depends(Provide[Container.detection_query_service])
    ],
    family: str | None = Query(None, description="Filter by taxonomic family"),
    genus: str | None = Query(None, description="Filter by genus"),
    order: str | None = Query(None, description="Filter by taxonomic order"),
    detection_filter: str = Query(
        "all", description="Filter by detection status: all, detected, undetected"
    ),
    sort_by: str = Query("name", description="Sort by: name, detected, count, latest"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=10, le=200, description="Items per page"),
) -> SpeciesChecklistResponse:
    """Get species checklist with detection status.

    This endpoint returns ALL species from the IOC reference database (not just detected ones),
    along with their detection status and counts. This is different from other endpoints which
    start from detections.

    Supports filtering by:
    - Taxonomy (family, genus, order)
    - Detection status (all, detected, undetected)
    """
    try:
        # Validate detection_filter parameter
        if detection_filter not in ["all", "detected", "undetected"]:
            raise HTTPException(
                status_code=400,
                detail="detection_filter must be 'all', 'detected', or 'undetected'",
            )

        # Get species checklist with detection status
        (
            species_list,
            total_count,
            detected_count,
            undetected_count,
        ) = await detection_query_service.get_species_checklist(
            family=family,
            genus=genus,
            order=order,
            detection_filter=detection_filter,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )

        # Convert to Pydantic models
        species_items = [SpeciesChecklistItem(**species) for species in species_list]

        # Calculate pagination metadata
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0
        has_prev = page > 1
        has_next = page < total_pages

        # Build filters dict
        filters = {
            "family": family,
            "genus": genus,
            "order": order,
            "detection_filter": detection_filter,
        }

        return SpeciesChecklistResponse(
            species=species_items,
            pagination=PaginationInfo(
                page=page,
                per_page=per_page,
                total=total_count,
                total_pages=total_pages,
                has_prev=has_prev,
                has_next=has_next,
            ),
            filters=filters,
            total_species=total_count,
            detected_species=detected_count,
            undetected_species=undetected_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting species checklist: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving species checklist") from e


@router.get("/{detection_id}/audio")
@inject
async def get_detection_audio(
    data_manager: Annotated[DataManager, Depends(Provide[Container.data_manager])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    detection_id: UUID,
) -> FileResponse:
    """Serve WAV audio file for a specific detection.

    Args:
        detection_id: UUID of the detection
        data_manager: Data manager for accessing detections
        path_resolver: Path resolver for getting data directory paths

    Returns:
        FileResponse with the WAV audio file

    Raises:
        HTTPException: If detection not found or audio file missing
    """
    try:
        # Get the detection with its audio file relationship
        detection = await data_manager.get_detection_by_id(detection_id)

        if not detection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Detection {detection_id} not found"
            )

        # Check if audio file exists
        if not detection.audio_file or not detection.audio_file.file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not available for this detection",
            )

        # Get the audio file path
        audio_path = detection.audio_file.file_path

        # If path is relative, resolve it against the recordings directory
        if not audio_path.is_absolute():
            audio_path = path_resolver.get_recordings_dir() / audio_path

        # Check if file exists on disk
        if not audio_path.exists():
            logger.warning("Audio file not found on disk: %s", audio_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found on disk"
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
        logger.error("Error serving audio for detection %s: %s", detection_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error serving audio file"
        ) from e


# === Detection Cleanup Routes ===


@router.post("/cleanup/preview", response_model=EBirdCleanupResponse)
@inject
async def preview_cleanup(
    request: EBirdCleanupPreviewRequest,
    cleanup_service: Annotated[
        DetectionCleanupService, Depends(Provide[Container.detection_cleanup_service])
    ],
) -> EBirdCleanupResponse:
    """Preview what would be deleted by detection cleanup without actually deleting.

    This endpoint analyzes existing detections against eBird regional confidence data
    and returns statistics about what would be removed based on the strictness level.

    Args:
        request: Preview request with strictness and region pack settings
        cleanup_service: Detection cleanup service

    Returns:
        Response with preview statistics
    """
    try:
        logger.info(
            "eBird cleanup preview requested: strictness=%s, region=%s",
            request.strictness,
            request.region_pack,
        )

        # Validate strictness level
        valid_strictness = ["vagrant", "rare", "uncommon", "common"]
        if request.strictness not in valid_strictness:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {', '.join(valid_strictness)}",
            )

        # Run preview
        stats = await cleanup_service.preview_cleanup(
            strictness=request.strictness,
            region_pack=request.region_pack,
            h3_resolution=request.h3_resolution,
            limit=request.limit,
        )

        logger.info(
            "Preview complete: %d detections checked, %d would be filtered",
            stats.total_checked,
            stats.total_filtered,
        )

        return EBirdCleanupResponse(
            success=True,
            message=(
                f"Preview complete: {stats.total_filtered} of {stats.total_checked} "
                f"detections would be removed with strictness '{request.strictness}'"
            ),
            stats=stats.to_dict(),
        )

    except FileNotFoundError as e:
        logger.error("eBird pack not found: %s", e)
        raise HTTPException(
            status_code=404,
            detail=f"eBird region pack not found: {request.region_pack}. "
            "Make sure the pack is installed in data/database/",
        ) from e
    except Exception as e:
        logger.exception("Error during eBird cleanup preview")
        raise HTTPException(status_code=500, detail=f"Failed to preview cleanup: {e!s}") from e


@router.post("/cleanup/execute", response_model=EBirdCleanupResponse)
@inject
async def execute_cleanup(
    request: EBirdCleanupRequest,
    cleanup_service: Annotated[
        DetectionCleanupService, Depends(Provide[Container.detection_cleanup_service])
    ],
) -> EBirdCleanupResponse:
    """Execute detection cleanup - remove detections that don't meet criteria.

    This endpoint permanently deletes detections and optionally their audio files
    based on eBird regional confidence data and strictness settings.

    **WARNING**: This operation cannot be undone. Use preview endpoint first.

    Args:
        request: Cleanup request with strictness, region pack, and confirmation
        cleanup_service: Detection cleanup service

    Returns:
        Response with deletion statistics
    """
    # Require confirmation for safety
    if not request.confirm:
        return EBirdCleanupResponse(
            success=False,
            message="Cleanup requires confirmation. Set 'confirm' to true.",
            stats=None,
        )

    try:
        logger.warning(
            "eBird cleanup execution requested: strictness=%s, region=%s, delete_audio=%s",
            request.strictness,
            request.region_pack,
            request.delete_audio,
        )

        # Validate strictness level
        valid_strictness = ["vagrant", "rare", "uncommon", "common"]
        if request.strictness not in valid_strictness:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {', '.join(valid_strictness)}",
            )

        # Execute cleanup
        stats = await cleanup_service.cleanup_detections(
            strictness=request.strictness,
            region_pack=request.region_pack,
            h3_resolution=request.h3_resolution,
            limit=request.limit,
            delete_audio=request.delete_audio,
        )

        logger.warning(
            "Cleanup complete: %d detections deleted, %d audio files deleted",
            stats.detections_deleted,
            stats.audio_files_deleted,
        )

        message_parts = [f"Cleanup complete: {stats.detections_deleted} detections deleted"]
        if request.delete_audio:
            message_parts.append(f"{stats.audio_files_deleted} audio files deleted")
            if stats.audio_deletion_errors > 0:
                message_parts.append(
                    f"({stats.audio_deletion_errors} audio file errors - check logs)"
                )

        return EBirdCleanupResponse(
            success=True,
            message=", ".join(message_parts),
            stats=stats.to_dict(),
        )

    except FileNotFoundError as e:
        logger.error("eBird pack not found: %s", e)
        raise HTTPException(
            status_code=404,
            detail=f"eBird region pack not found: {request.region_pack}. "
            "Make sure the pack is installed in data/database/",
        ) from e
    except Exception as e:
        logger.exception("Error during eBird cleanup execution")
        raise HTTPException(status_code=500, detail=f"Failed to execute cleanup: {e!s}") from e
