"""Tests for detection cleanup service."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.engine import Result as ResultType

from birdnetpi.config.models import EBirdFilterConfig
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.detections.cleanup import CleanupStats, DetectionCleanupService
from birdnetpi.detections.models import AudioFile, Detection

# Using test_config and db_service_factory from global fixtures in conftest.py


@pytest.fixture
def cleanup_service_factory(db_service_factory, async_mock_factory, path_resolver, test_config):
    """Create cleanup service with configured dependencies.

    This factory bundles together all the mocks needed for cleanup tests:
    - CoreDatabaseService (via db_service_factory)
    - EBirdRegionService (via async_mock_factory)
    - PathResolver (global fixture)
    - BirdNETConfig (global test_config fixture)

    Returns a tuple of (cleanup_service, core_db, session, result, ebird_service)
    so tests can configure the mocks as needed.
    """

    def _create_cleanup_service(
        session_config: dict | None = None,
        ebird_config: dict | None = None,
    ):
        # Configure test_config with eBird filtering settings
        test_config.ebird_filtering = EBirdFilterConfig(
            enabled=True,
            region_pack="test-pack-2025.08",
            h3_resolution=5,
            detection_mode="filter",
            detection_strictness="vagrant",
            unknown_species_behavior="allow",
        )

        # Create database service using global factory
        core_db, session, result = db_service_factory(session_config=session_config)

        # Create eBird service using global async_mock_factory
        ebird_defaults = {
            "attach_to_session": None,
            "detach_from_session": None,
            "get_species_confidence_tier": "vagrant",
        }
        if ebird_config:
            ebird_defaults.update(ebird_config)
        ebird_service = async_mock_factory(EBirdRegionService, **ebird_defaults)

        # Create cleanup service
        cleanup_svc = DetectionCleanupService(
            core_db=core_db,
            ebird_service=ebird_service,
            path_resolver=path_resolver,
            config=test_config,
        )

        return cleanup_svc, core_db, session, result, ebird_service

    return _create_cleanup_service


@pytest.fixture
def cleanup_service(cleanup_service_factory):
    """Create cleanup service with default configuration."""
    cleanup_svc, _, _, _, _ = cleanup_service_factory()
    return cleanup_svc


@pytest.fixture
def sample_detection():
    """Create a sample detection for testing."""
    return Detection(
        id=uuid4(),
        species_tensor="Cyanocitta cristata_Blue Jay",
        scientific_name="Cyanocitta cristata",
        common_name="Blue Jay",
        confidence=0.85,
        timestamp=datetime.now(),
        latitude=43.6532,
        longitude=-79.3832,
        species_confidence_threshold=0.7,
        week=1,
        sensitivity_setting=1.5,
        overlap=0.0,
        audio_file_id=uuid4(),
    )


class TestCleanupStatsInitialization:
    """Test CleanupStats dataclass."""

    def test_cleanup_stats_defaults(self):
        """Should initialize with default values."""
        stats = CleanupStats()

        assert stats.total_checked == 0
        assert stats.total_filtered == 0
        assert stats.detections_deleted == 0
        assert stats.audio_files_deleted == 0
        assert stats.audio_deletion_errors == 0
        assert stats.strictness_level == ""
        assert stats.region_pack == ""
        assert stats.started_at is None
        assert stats.completed_at is None

    def test_cleanup_stats_to_dict(self):
        """Should convert to dictionary for JSON serialization."""
        started = datetime.now()
        completed = datetime.now()

        stats = CleanupStats(
            total_checked=100,
            total_filtered=25,
            detections_deleted=25,
            audio_files_deleted=20,
            audio_deletion_errors=5,
            strictness_level="vagrant",
            region_pack="test-pack",
            started_at=started,
            completed_at=completed,
        )

        result = stats.to_dict()

        assert result["total_checked"] == 100
        assert result["total_filtered"] == 25
        assert result["detections_deleted"] == 25
        assert result["audio_files_deleted"] == 20
        assert result["audio_deletion_errors"] == 5
        assert result["strictness_level"] == "vagrant"
        assert result["region_pack"] == "test-pack"
        assert result["started_at"] == started.isoformat()
        assert result["completed_at"] == completed.isoformat()


class TestPreviewCleanup:
    """Test preview cleanup functionality."""

    @pytest.mark.asyncio
    async def test_preview_cleanup_no_detections(self, cleanup_service_factory):
        """Should return zero counts when no detections found."""
        # Create cleanup service with empty detections
        cleanup_svc, *_ = cleanup_service_factory(session_config={"fetch_results": []})

        stats = await cleanup_svc.preview_cleanup(strictness="vagrant", region_pack="test-pack")

        assert stats.total_checked == 0
        assert stats.total_filtered == 0
        assert stats.strictness_level == "vagrant"
        assert stats.region_pack == "test-pack"
        assert stats.started_at is not None
        assert stats.completed_at is not None

    @pytest.mark.asyncio
    async def test_preview_cleanup_with_detections(self, cleanup_service_factory, sample_detection):
        """Should count detections that would be filtered."""
        # Create cleanup service with sample detection that will be filtered
        cleanup_svc, _, _, _, ebird_service = cleanup_service_factory(
            session_config={"fetch_results": [sample_detection]},
            ebird_config={"get_species_confidence_tier": "vagrant"},
        )

        stats = await cleanup_svc.preview_cleanup(strictness="vagrant", region_pack="test-pack")

        assert stats.total_checked == 1
        assert stats.total_filtered == 1
        # Detach should be called
        ebird_service.detach_from_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_cleanup_with_limit(self, cleanup_service_factory, sample_detection):
        """Should respect limit parameter."""
        cleanup_svc, _, session, _, _ = cleanup_service_factory(
            session_config={"fetch_results": [sample_detection]}
        )

        await cleanup_svc.preview_cleanup(strictness="vagrant", region_pack="test-pack", limit=10)

        # Verify limit was passed to query
        call_args = session.execute.call_args[0][0]
        # The limit should be set on the statement
        assert hasattr(call_args, "_limit_clause")


class TestCleanupDetections:
    """Test actual cleanup execution."""

    @pytest.mark.asyncio
    async def test_cleanup_detections_no_matches(self, cleanup_service_factory):
        """Should perform cleanup when no detections match filter."""
        cleanup_svc, _, _, _, _ = cleanup_service_factory(session_config={"fetch_results": []})

        stats = await cleanup_svc.cleanup_detections(
            strictness="vagrant", region_pack="test-pack", delete_audio=True
        )

        assert stats.total_checked == 0
        assert stats.total_filtered == 0
        assert stats.detections_deleted == 0
        assert stats.audio_files_deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_detections_with_matches(
        self, cleanup_service_factory, sample_detection, db_service_factory
    ):
        """Should delete detections that match filter criteria."""
        # Need to configure multiple execute calls, so configure the session directly
        core_db, session, result = db_service_factory()

        # Mock detections query
        result.scalars.return_value.all.return_value = [sample_detection]

        # Mock subsequent queries for audio file and detection deletion

        mock_audio_result = MagicMock(spec=ResultType)
        mock_audio_result.scalar_one_or_none.return_value = None

        mock_det_result = MagicMock(spec=ResultType)
        mock_det_result.scalar_one_or_none.return_value = sample_detection

        session.execute = AsyncMock(
            spec=object, side_effect=[result, mock_audio_result, mock_det_result]
        )

        # Create cleanup service with manually configured database
        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )
        # Override the core_db to use our specially configured one
        cleanup_svc.core_db = core_db

        stats = await cleanup_svc.cleanup_detections(
            strictness="vagrant", region_pack="test-pack", delete_audio=False
        )

        assert stats.total_checked == 1
        assert stats.total_filtered == 1
        assert stats.detections_deleted == 1
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_detections_with_audio_files(
        self, cleanup_service_factory, db_service_factory, path_resolver, tmp_path
    ):
        """Should delete audio files when delete_audio=True."""
        # Create test audio file
        recordings_dir = tmp_path / "recordings"
        recordings_dir.mkdir()
        audio_file_path = recordings_dir / "test_audio.wav"
        audio_file_path.touch()

        # Override the method on path_resolver to return our test directory
        path_resolver.get_recordings_dir = lambda: recordings_dir

        # Create detection with audio file
        audio_file_id = uuid4()
        detection = Detection(
            id=uuid4(),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.85,
            timestamp=datetime.now(),
            latitude=43.6532,
            longitude=-79.3832,
            audio_file_id=audio_file_id,
        )

        audio_file = AudioFile(id=audio_file_id, file_path=Path("test_audio.wav"))

        # Configure database with multiple execute calls
        core_db, session, result = db_service_factory()

        # Mock query results
        result.scalars.return_value.all.return_value = [detection]

        # Mock subsequent queries

        mock_audio_query_result = MagicMock(spec=ResultType)
        mock_audio_query_result.scalar_one_or_none.return_value = audio_file

        mock_audio_del_result = MagicMock(spec=ResultType)
        mock_audio_del_result.scalar_one_or_none.return_value = detection

        mock_audio_file_del_result = MagicMock(spec=ResultType)
        mock_audio_file_del_result.scalar_one_or_none.return_value = audio_file

        mock_det_del_result = MagicMock(spec=ResultType)
        mock_det_del_result.scalar_one_or_none.return_value = detection

        session.execute = AsyncMock(
            spec=object,
            side_effect=[
                result,  # Initial detections query
                mock_audio_query_result,  # Audio file query for collection
                mock_audio_del_result,  # Detection query for deletion
                mock_audio_file_del_result,  # Audio file query for deletion
                mock_det_del_result,  # Detection deletion
            ],
        )

        # Create cleanup service
        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )
        cleanup_svc.core_db = core_db

        stats = await cleanup_svc.cleanup_detections(
            strictness="vagrant", region_pack="test-pack", delete_audio=True
        )

        assert stats.audio_files_deleted == 1
        assert not audio_file_path.exists()

    @pytest.mark.asyncio
    async def test_cleanup_detections_audio_deletion_error(
        self, cleanup_service_factory, db_service_factory, path_resolver, tmp_path
    ):
        """Should handle audio file deletion errors gracefully."""
        # Create detection with audio file pointing to non-existent file
        audio_file_id = uuid4()
        detection = Detection(
            id=uuid4(),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.85,
            timestamp=datetime.now(),
            latitude=43.6532,
            longitude=-79.3832,
            audio_file_id=audio_file_id,
        )

        audio_file = AudioFile(id=audio_file_id, file_path=Path("nonexistent.wav"))

        # Configure database with multiple execute calls
        core_db, session, result = db_service_factory()

        result.scalars.return_value.all.return_value = [detection]

        mock_audio_query_result = MagicMock(spec=ResultType)
        mock_audio_query_result.scalar_one_or_none.return_value = audio_file

        mock_audio_del_result = MagicMock(spec=ResultType)
        mock_audio_del_result.scalar_one_or_none.return_value = detection

        mock_audio_file_del_result = MagicMock(spec=ResultType)
        mock_audio_file_del_result.scalar_one_or_none.return_value = audio_file

        mock_det_del_result = MagicMock(spec=ResultType)
        mock_det_del_result.scalar_one_or_none.return_value = detection

        session.execute = AsyncMock(
            spec=object,
            side_effect=[
                result,
                mock_audio_query_result,
                mock_audio_del_result,
                mock_audio_file_del_result,
                mock_det_del_result,
            ],
        )

        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )
        cleanup_svc.core_db = core_db

        stats = await cleanup_svc.cleanup_detections(
            strictness="vagrant", region_pack="test-pack", delete_audio=True
        )

        # Should not fail, but should record error
        assert stats.audio_files_deleted == 0
        assert stats.audio_deletion_errors == 0  # File doesn't exist, no error


class TestShouldFilterDetection:
    """Test detection filtering logic."""

    @pytest.mark.asyncio
    async def test_should_filter_detection_vagrant(
        self, cleanup_service_factory, sample_detection, db_service_factory
    ):
        """Should filter vagrant species with vagrant strictness."""
        _, session, _ = db_service_factory()
        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )

        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="vagrant",
            h3_resolution=5,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_should_filter_detection_rare(
        self, cleanup_service_factory, sample_detection, db_service_factory, async_mock_factory
    ):
        """Should filter vagrant and rare with rare strictness."""
        _, session, _ = db_service_factory()

        # Test vagrant
        cleanup_svc, _, _, _, ebird_svc = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="rare",
            h3_resolution=5,
        )
        assert result is True

        # Test rare
        ebird_svc.get_species_confidence_tier.return_value = "rare"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="rare",
            h3_resolution=5,
        )
        assert result is True

        # Test uncommon (should not filter)
        ebird_svc.get_species_confidence_tier.return_value = "uncommon"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="rare",
            h3_resolution=5,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_should_filter_detection_uncommon(
        self, cleanup_service_factory, sample_detection, db_service_factory
    ):
        """Should only allow common species with uncommon strictness."""
        _, session, _ = db_service_factory()
        cleanup_svc, _, _, _, ebird_svc = cleanup_service_factory()

        # Test vagrant (filtered)
        ebird_svc.get_species_confidence_tier.return_value = "vagrant"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="uncommon",
            h3_resolution=5,
        )
        assert result is True

        # Test rare (filtered)
        ebird_svc.get_species_confidence_tier.return_value = "rare"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="uncommon",
            h3_resolution=5,
        )
        assert result is True

        # Test uncommon (filtered)
        ebird_svc.get_species_confidence_tier.return_value = "uncommon"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="uncommon",
            h3_resolution=5,
        )
        assert result is True

        # Test common (not filtered)
        ebird_svc.get_species_confidence_tier.return_value = "common"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="uncommon",
            h3_resolution=5,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_should_filter_detection_common(
        self, cleanup_service_factory, sample_detection, db_service_factory
    ):
        """Should only allow common species with common strictness."""
        _, session, _ = db_service_factory()
        cleanup_svc, _, _, _, ebird_svc = cleanup_service_factory()

        # Test all non-common tiers (all filtered)
        for tier in ["vagrant", "rare", "uncommon"]:
            ebird_svc.get_species_confidence_tier.return_value = tier
            result = await cleanup_svc._should_filter_detection(
                session=session,
                detection=sample_detection,
                strictness="common",
                h3_resolution=5,
            )
            assert result is True

        # Test common (not filtered)
        ebird_svc.get_species_confidence_tier.return_value = "common"
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="common",
            h3_resolution=5,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_should_filter_detection_unknown_species_allow(
        self, cleanup_service_factory, sample_detection, db_service_factory
    ):
        """Should not filter unknown species when behavior is allow."""
        _, session, _ = db_service_factory()
        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": None}
        )

        # Default behavior is allow
        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="vagrant",
            h3_resolution=5,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_should_filter_detection_unknown_species_block(
        self, cleanup_service_factory, sample_detection, db_service_factory, test_config
    ):
        """Should filter unknown species when behavior is block."""
        _, session, _ = db_service_factory()

        # Change config to block unknown species
        test_config.ebird_filtering.unknown_species_behavior = "block"

        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": None}
        )

        result = await cleanup_svc._should_filter_detection(
            session=session,
            detection=sample_detection,
            strictness="vagrant",
            h3_resolution=5,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_should_filter_detection_no_coordinates(
        self, cleanup_service_factory, db_service_factory
    ):
        """Should not filter detections without coordinates."""
        detection = Detection(
            id=uuid4(),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.85,
            timestamp=datetime.now(),
            latitude=None,  # No coordinates
            longitude=None,
        )

        _, session, _ = db_service_factory()
        cleanup_svc, _, _, _, _ = cleanup_service_factory()

        result = await cleanup_svc._should_filter_detection(
            session=session, detection=detection, strictness="vagrant", h3_resolution=5
        )

        assert result is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_cleanup_detections_detach_on_error(
        self, cleanup_service_factory, db_service_factory
    ):
        """Should detach database even if cleanup fails."""
        core_db, session, _ = db_service_factory()

        # Make execute raise an exception
        session.execute = AsyncMock(spec=object, side_effect=Exception("Database error"))

        cleanup_svc, _, _, _, ebird_service = cleanup_service_factory()
        cleanup_svc.core_db = core_db

        # The exception will be caught by the context manager
        # but detach should still be called in the finally block
        try:
            await cleanup_svc.cleanup_detections(strictness="vagrant", region_pack="test-pack")
        except Exception:
            pass  # Expected to be caught by context manager

        # Detach should still be called in finally block
        ebird_service.detach_from_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_detections_empty_scientific_name(
        self, cleanup_service_factory, db_service_factory
    ):
        """Should handle detections with empty scientific name."""
        detection = Detection(
            id=uuid4(),
            species_tensor="_Unknown",  # Empty scientific name
            scientific_name="",  # Empty
            common_name="Unknown",
            confidence=0.85,
            timestamp=datetime.now(),
            latitude=43.6532,
            longitude=-79.3832,
        )

        cleanup_svc, _, _, _, ebird_service = cleanup_service_factory(
            session_config={"fetch_results": [detection]},
            ebird_config={"get_species_confidence_tier": None},
        )

        stats = await cleanup_svc.preview_cleanup(strictness="vagrant", region_pack="test-pack")

        # Should check the detection even with empty name
        assert stats.total_checked == 1
        assert ebird_service.get_species_confidence_tier.called

    @pytest.mark.asyncio
    async def test_cleanup_detections_absolute_audio_path(
        self, cleanup_service_factory, db_service_factory, tmp_path
    ):
        """Should handle absolute audio file paths."""
        # Create test audio file
        absolute_audio_path = tmp_path / "absolute" / "test_audio.wav"
        absolute_audio_path.parent.mkdir(parents=True)
        absolute_audio_path.touch()

        audio_file_id = uuid4()
        detection = Detection(
            id=uuid4(),
            species_tensor="Cyanocitta cristata_Blue Jay",
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.85,
            timestamp=datetime.now(),
            latitude=43.6532,
            longitude=-79.3832,
            audio_file_id=audio_file_id,
        )

        audio_file = AudioFile(id=audio_file_id, file_path=absolute_audio_path)

        # Configure database with multiple execute calls
        core_db, session, result = db_service_factory()

        result.scalars.return_value.all.return_value = [detection]

        mock_audio_query_result = MagicMock(spec=ResultType)
        mock_audio_query_result.scalar_one_or_none.return_value = audio_file

        mock_audio_del_result = MagicMock(spec=ResultType)
        mock_audio_del_result.scalar_one_or_none.return_value = detection

        mock_audio_file_del_result = MagicMock(spec=ResultType)
        mock_audio_file_del_result.scalar_one_or_none.return_value = audio_file

        mock_det_del_result = MagicMock(spec=ResultType)
        mock_det_del_result.scalar_one_or_none.return_value = detection

        session.execute = AsyncMock(
            spec=object,
            side_effect=[
                result,
                mock_audio_query_result,
                mock_audio_del_result,
                mock_audio_file_del_result,
                mock_det_del_result,
            ],
        )

        cleanup_svc, _, _, _, _ = cleanup_service_factory(
            ebird_config={"get_species_confidence_tier": "vagrant"}
        )
        cleanup_svc.core_db = core_db

        stats = await cleanup_svc.cleanup_detections(
            strictness="vagrant", region_pack="test-pack", delete_audio=True
        )

        assert stats.audio_files_deleted == 1
        assert not absolute_audio_path.exists()
