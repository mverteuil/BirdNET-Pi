"""Detection cleanup service for eBird regional filtering.

This service provides bulk cleanup of existing detections based on eBird regional
confidence data. It identifies detections that don't meet configured strictness
criteria and removes them along with their associated audio files.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

import h3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics from a cleanup operation."""

    total_checked: int = 0
    total_filtered: int = 0
    detections_deleted: int = 0
    audio_files_deleted: int = 0
    audio_deletion_errors: int = 0
    strictness_level: str = ""
    region_pack: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_checked": self.total_checked,
            "total_filtered": self.total_filtered,
            "detections_deleted": self.detections_deleted,
            "audio_files_deleted": self.audio_files_deleted,
            "audio_deletion_errors": self.audio_deletion_errors,
            "strictness_level": self.strictness_level,
            "region_pack": self.region_pack,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DetectionCleanupService:
    """Service for bulk cleanup of detections based on eBird filtering rules."""

    def __init__(
        self,
        core_db: CoreDatabaseService,
        ebird_service: EBirdRegionService,
        path_resolver: PathResolver,
        config: BirdNETConfig,
    ):
        """Initialize the cleanup service.

        Args:
            core_db: Core database service for detection queries
            ebird_service: eBird region service for confidence lookups
            path_resolver: Path resolver for locating audio files
            config: Application configuration
        """
        self.core_db = core_db
        self.ebird_service = ebird_service
        self.path_resolver = path_resolver
        self.config = config

    async def preview_cleanup(
        self,
        strictness: str,
        region_pack: str,
        h3_resolution: int = 5,
        limit: int | None = None,
    ) -> CleanupStats:
        """Preview what would be deleted without actually deleting.

        Args:
            strictness: Strictness level (vagrant, rare, uncommon, common)
            region_pack: Name of the region pack to use
            h3_resolution: H3 resolution for lookups (default: 5)
            limit: Optional limit on number of detections to check

        Returns:
            CleanupStats with counts of what would be deleted
        """
        stats = CleanupStats(
            strictness_level=strictness,
            region_pack=region_pack,
            started_at=datetime.now(),
        )

        async with self.core_db.get_async_db() as session:
            # Attach eBird pack
            await self.ebird_service.attach_to_session(session, region_pack)

            try:
                # Query all detections with coordinates
                stmt = select(Detection).where(
                    Detection.latitude != None,  # noqa: E711
                    Detection.longitude != None,  # noqa: E711
                )
                if limit:
                    stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                detections = result.scalars().all()

                stats.total_checked = len(detections)

                # Check each detection against eBird filtering
                for detection in detections:
                    if await self._should_filter_detection(
                        session=session,
                        detection=detection,
                        strictness=strictness,
                        h3_resolution=h3_resolution,
                    ):
                        stats.total_filtered += 1

            finally:
                await self.ebird_service.detach_from_session(session)

        stats.completed_at = datetime.now()
        return stats

    async def cleanup_detections(
        self,
        strictness: str,
        region_pack: str,
        h3_resolution: int = 5,
        limit: int | None = None,
        delete_audio: bool = True,
    ) -> CleanupStats:
        """Clean up detections that don't meet eBird confidence criteria.

        Args:
            strictness: Strictness level (vagrant, rare, uncommon, common)
            region_pack: Name of the region pack to use
            h3_resolution: H3 resolution for lookups (default: 5)
            limit: Optional limit on number of detections to process
            delete_audio: Whether to delete associated audio files (default: True)

        Returns:
            CleanupStats with deletion counts and timing
        """
        stats = CleanupStats(
            strictness_level=strictness,
            region_pack=region_pack,
            started_at=datetime.now(),
        )

        async with self.core_db.get_async_db() as session:
            # Attach eBird pack
            await self.ebird_service.attach_to_session(session, region_pack)

            try:
                # Query all detections with coordinates
                stmt = select(Detection).where(
                    Detection.latitude != None,  # noqa: E711
                    Detection.longitude != None,  # noqa: E711
                )
                if limit:
                    stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                detections = result.scalars().all()

                stats.total_checked = len(detections)

                # Collect detections and audio files to delete
                detections_to_delete, audio_files_to_delete = await self._collect_items_to_delete(
                    session=session,
                    detections=detections,
                    strictness=strictness,
                    h3_resolution=h3_resolution,
                    delete_audio=delete_audio,
                    stats=stats,
                )

                # Delete detections from database
                if detections_to_delete:
                    await self._delete_detections_from_database(
                        session, detections_to_delete, stats
                    )

                # Delete audio files from disk
                if delete_audio and audio_files_to_delete:
                    await self._delete_audio_files_from_disk(audio_files_to_delete, stats)

            finally:
                await self.ebird_service.detach_from_session(session)

        stats.completed_at = datetime.now()
        return stats

    async def _delete_detections_from_database(
        self,
        session: AsyncSession,
        detection_ids: list[UUID],
        stats: CleanupStats,
    ) -> None:
        """Delete detections and their audio files from database.

        Args:
            session: Database session
            detection_ids: List of detection IDs to delete
            stats: Statistics object to update
        """
        for detection_id in detection_ids:
            # Delete associated audio file record first (FK constraint)
            audio_delete_stmt = select(Detection).where(Detection.id == detection_id)
            det_result = await session.execute(audio_delete_stmt)
            det = det_result.scalar_one_or_none()
            if det and det.audio_file_id:
                audio_file_delete_stmt = select(AudioFile).where(AudioFile.id == det.audio_file_id)
                af_result = await session.execute(audio_file_delete_stmt)
                af = af_result.scalar_one_or_none()
                if af:
                    await session.delete(af)

            # Delete detection
            detection_delete_stmt = select(Detection).where(Detection.id == detection_id)
            d_result = await session.execute(detection_delete_stmt)
            d = d_result.scalar_one_or_none()
            if d:
                await session.delete(d)
                stats.detections_deleted += 1

        await session.commit()
        logger.info("Deleted %d detections from database", stats.detections_deleted)

    async def _should_filter_detection(
        self,
        session: AsyncSession,
        detection: Detection,
        strictness: str,
        h3_resolution: int,
    ) -> bool:
        """Check if a detection should be filtered based on eBird criteria.

        Args:
            session: Database session with eBird pack attached
            detection: Detection to check
            strictness: Strictness level
            h3_resolution: H3 resolution for lookups

        Returns:
            True if detection should be filtered (deleted)
        """
        # Skip detections without coordinates
        if detection.latitude is None or detection.longitude is None:
            return False

        # Convert to H3 cell
        h3_cell = h3.latlng_to_cell(detection.latitude, detection.longitude, h3_resolution)

        # Query confidence tier
        confidence_tier = await self.ebird_service.get_species_confidence_tier(
            session, detection.scientific_name, h3_cell
        )

        # Unknown species - use configured behavior
        if confidence_tier is None:
            # For cleanup, we default to "allow" (don't delete unknown species)
            # This is safer - user can change to "block" if desired
            return self.config.ebird_filtering.unknown_species_behavior == "block"

        # Apply strictness filtering
        if strictness == "vagrant":
            return confidence_tier == "vagrant"
        elif strictness == "rare":
            return confidence_tier in ["vagrant", "rare"]
        elif strictness == "uncommon":
            return confidence_tier in ["vagrant", "rare", "uncommon"]
        elif strictness == "common":
            return confidence_tier != "common"

        return False

    async def _collect_items_to_delete(
        self,
        session: AsyncSession,
        detections: list[Detection],
        strictness: str,
        h3_resolution: int,
        delete_audio: bool,
        stats: CleanupStats,
    ) -> tuple[list[UUID], list[Path]]:
        """Collect detections and audio files to delete.

        Args:
            session: Database session
            detections: List of detections to check
            strictness: Strictness level
            h3_resolution: H3 resolution for lookups
            delete_audio: Whether to collect audio file paths
            stats: Statistics object to update

        Returns:
            Tuple of (detection_ids, audio_file_paths)
        """
        detections_to_delete: list[UUID] = []
        audio_files_to_delete: list[Path] = []

        for detection in detections:
            if await self._should_filter_detection(
                session=session,
                detection=detection,
                strictness=strictness,
                h3_resolution=h3_resolution,
            ):
                stats.total_filtered += 1
                detections_to_delete.append(detection.id)

                # Collect audio file path if it exists
                if delete_audio and detection.audio_file_id:
                    audio_file_stmt = select(AudioFile).where(
                        AudioFile.id == detection.audio_file_id
                    )
                    audio_result = await session.execute(audio_file_stmt)
                    audio_file = audio_result.scalar_one_or_none()
                    if audio_file and audio_file.file_path:
                        # Resolve path
                        if audio_file.file_path.is_absolute():
                            audio_files_to_delete.append(audio_file.file_path)
                        else:
                            audio_files_to_delete.append(
                                self.path_resolver.get_recordings_dir() / audio_file.file_path
                            )

        return detections_to_delete, audio_files_to_delete

    async def _delete_audio_files_from_disk(
        self, audio_files: list[Path], stats: CleanupStats
    ) -> None:
        """Delete audio files from disk.

        Args:
            audio_files: List of audio file paths to delete
            stats: Statistics object to update
        """
        for audio_path in audio_files:
            try:
                if audio_path.exists():
                    audio_path.unlink()
                    stats.audio_files_deleted += 1
            except Exception as e:
                logger.error("Failed to delete audio file %s: %s", audio_path, e)
                stats.audio_deletion_errors += 1

        logger.info("Deleted %d audio files from disk", stats.audio_files_deleted)
