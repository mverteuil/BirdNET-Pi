"""Comprehensive tests for DetectionQueryService to improve coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection, DetectionWithTaxa
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.species.display import SpeciesDisplayService


@pytest.fixture
def mock_core_database():
    """Mock core database."""
    mock = MagicMock(spec=CoreDatabaseService)
    mock.get_async_db = MagicMock()
    return mock


@pytest.fixture
def mock_species_database():
    """Mock species database."""
    mock = MagicMock(spec=SpeciesDatabaseService)
    mock.attach_all_to_session = AsyncMock()
    mock.detach_all_from_session = AsyncMock()
    return mock


@pytest.fixture
def mock_species_display():
    """Mock species display service."""
    mock = MagicMock(spec=SpeciesDisplayService)
    mock.format_species_name = Mock(return_value="Formatted Species")
    return mock


@pytest.fixture
def detection_query_service(mock_core_database, mock_species_database, mock_species_display):
    """Create DetectionQueryService with mocks."""
    return DetectionQueryService(
        core_database=mock_core_database,
        species_database=mock_species_database,
        species_display_service=mock_species_display,
    )


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    return session


@pytest.fixture
def sample_detection():
    """Create a sample detection for testing."""
    return Detection(
        id=uuid4(),
        species_tensor="Test species",
        scientific_name="Testicus species",
        common_name="Test Bird",
        confidence=0.85,
        timestamp=datetime.now(UTC),
        audio_file_id=uuid4(),
    )


class TestDateAndTimeParsing:
    """Test date and time parsing functionality."""

    def test_parse_timestamp_numeric_as_string(self, detection_query_service):
        """Should parse numeric timestamps when provided as strings."""
        # The implementation converts to string then parses as ISO format
        # So we need to provide ISO format strings
        timestamp_str = "2024-01-01T00:00:00"
        result = detection_query_service._parse_timestamp(timestamp_str)
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_parse_timestamp_with_timezone(self, detection_query_service):
        """Should parse timestamps with timezone info."""
        timestamp_str = "2024-01-01T12:00:00+00:00"
        result = detection_query_service._parse_timestamp(timestamp_str)
        assert isinstance(result, datetime)


class TestFilterMethods:
    """Test filter application methods."""

    def test_apply_date_filters_both(self, detection_query_service):
        """Should apply both start and end date filters."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        filtered = detection_query_service._apply_date_filters(stmt, start, end)

        query_str = str(filtered)
        assert "timestamp >=" in query_str
        assert "timestamp <=" in query_str

    def test_apply_date_filters_start_only(self, detection_query_service):
        """Should apply only start date filter."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        start = datetime(2024, 1, 1)

        filtered = detection_query_service._apply_date_filters(stmt, start, None)

        assert "timestamp >=" in str(filtered)
        assert "timestamp <=" not in str(filtered)

    def test_apply_date_filters_end_only(self, detection_query_service):
        """Should apply only end date filter."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        end = datetime(2024, 1, 31)

        filtered = detection_query_service._apply_date_filters(stmt, None, end)

        assert "timestamp <=" in str(filtered)
        assert "timestamp >=" not in str(filtered)

    def test_apply_confidence_filters_both(self, detection_query_service):
        """Should apply both min and max confidence filters."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, 0.5, 0.9)

        query_str = str(filtered)
        assert "confidence >=" in query_str
        assert "confidence <=" in query_str

    def test_apply_confidence_filters_min_only(self, detection_query_service):
        """Should apply only min confidence filter."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, 0.5, None)

        assert "confidence >=" in str(filtered)

    def test_apply_confidence_filters_max_only(self, detection_query_service):
        """Should apply only max confidence filter."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, None, 0.9)

        assert "confidence <=" in str(filtered)

    def test_apply_ordering_default_column(self, detection_query_service):
        """Should use default column when invalid order_by specified."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        ordered = detection_query_service._apply_ordering(stmt, "invalid_column", True)

        # Should default to timestamp
        assert "ORDER BY" in str(ordered)

    def test_apply_ordering_ascending(self, detection_query_service):
        """Should apply ascending order."""
        from sqlalchemy import select

        from birdnetpi.detections.models import Detection

        stmt = select(Detection)
        ordered = detection_query_service._apply_ordering(stmt, "confidence", False)

        query_str = str(ordered)
        assert "ORDER BY" in query_str
        assert "DESC" not in query_str


class TestMainQueryMethods:
    """Test main query methods."""

    @pytest.mark.asyncio
    async def test_query_detections_delegates(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should delegate to _execute_join_query."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Mock the internal method
        with patch.object(
            detection_query_service, "_execute_join_query", new_callable=AsyncMock
        ) as mock_method:
            mock_method.return_value = []

            # Call query_detections
            await detection_query_service.query_detections(
                species="Turdus migratorius",
                family="Turdidae",
                genus="Turdus",
                min_confidence=0.7,
            )

            # Verify delegation - when no limit is specified, it's passed as None
            mock_method.assert_called_once_with(
                session=mock_session,
                limit=None,  # No limit specified, so None is passed
                offset=0,
                language_code="en",
                start_date=None,
                end_date=None,
                scientific_name_filter="Turdus migratorius",
                family_filter="Turdidae",
                genus_filter="Turdus",
                min_confidence=0.7,
                max_confidence=None,
                order_by="timestamp",
                order_desc=True,
            )

    @pytest.mark.asyncio
    async def test_get_detections_with_taxa_legacy_since(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should support legacy 'since' parameter."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Test with since parameter
        since_date = datetime(2024, 1, 1)
        result = await detection_query_service.get_detections_with_taxa(since=since_date)

        # Should execute query
        mock_session.execute.assert_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_detections_with_taxa_full_filters(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should apply all filters in get_detections_with_taxa."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Test with all filters
        await detection_query_service.get_detections_with_taxa(
            limit=50,
            offset=10,
            language_code="fr",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            scientific_name_filter=["Species1", "Species2"],
            family_filter="Turdidae",
            genus_filter="Turdus",
            min_confidence=0.6,
            max_confidence=0.95,
            order_by="confidence",
            order_desc=False,
        )

        # Should execute query
        mock_session.execute.assert_called()
        # Check that species databases were attached/detached
        mock_species_database.attach_all_to_session.assert_called()
        mock_species_database.detach_all_from_session.assert_called()

    @pytest.mark.asyncio
    async def test_get_detection_with_taxa_found(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should return detection with taxa when found."""
        # Setup mock
        mock_session = AsyncMock()
        detection_id = uuid4()

        # Mock result row
        mock_row = MagicMock()
        mock_row.id = str(detection_id)
        mock_row.species_tensor = "tensor"
        mock_row.scientific_name = "Turdus migratorius"
        mock_row.common_name = "American Robin"
        mock_row.confidence = 0.9
        mock_row.timestamp = "2024-01-15T10:30:00"
        mock_row.audio_file_id = str(uuid4())
        mock_row.latitude = 45.5
        mock_row.longitude = -73.6
        mock_row.species_confidence_threshold = 0.7
        mock_row.week = 3
        mock_row.sensitivity_setting = 1.5
        mock_row.overlap = 2.0
        mock_row.ioc_english_name = "American Robin"
        mock_row.translated_name = "Merle d'Amérique"
        mock_row.family = "Turdidae"
        mock_row.genus = "Turdus"
        mock_row.order_name = "Passeriformes"

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.get_detection_with_taxa(detection_id, "fr")

        # Verify
        assert result is not None
        assert isinstance(result, DetectionWithTaxa)
        assert result.family == "Turdidae"
        assert result.genus == "Turdus"
        assert result.order_name == "Passeriformes"

    @pytest.mark.asyncio
    async def test_get_detection_with_taxa_not_found(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should return None when detection not found."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.get_detection_with_taxa(uuid4())

        # Verify
        assert result is None


class TestSummaryMethods:
    """Test summary and aggregation methods."""

    @pytest.mark.asyncio
    async def test_get_species_summary(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should get species summary with counts."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock species results - need to mock fetchall() not mappings()
        mock_rows = [
            MagicMock(
                scientific_name="Species1",
                detection_count=50,
                avg_confidence=0.75,
                latest_detection="2024-01-15T16:00:00",
                ioc_english_name="Bird 1",
                translated_name="Oiseau 1",
                family="Turdidae",
                genus="Turdus",
                order_name="Passeriformes",
            ),
            MagicMock(
                scientific_name="Species2",
                detection_count=30,
                avg_confidence=0.8,
                latest_detection="2024-01-14T17:00:00",
                ioc_english_name="Bird 2",
                translated_name="Oiseau 2",
                family="Turdidae",
                genus="Turdus",
                order_name="Passeriformes",
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.get_species_summary(
            language_code="en", since=datetime(2024, 1, 1), family_filter="Turdidae"
        )

        # Verify
        assert len(result) == 2
        assert result[0]["scientific_name"] == "Species1"
        assert result[0]["detection_count"] == 50
        assert result[1]["scientific_name"] == "Species2"

    @pytest.mark.asyncio
    async def test_get_family_summary(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should get family summary with counts."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock family results - need to mock fetchall() not mappings()
        mock_rows = [
            MagicMock(
                family="Turdidae",
                order_name="Passeriformes",
                detection_count=100,
                species_count=5,
                avg_confidence=0.78,
                latest_detection="2024-01-20T18:00:00",
            ),
            MagicMock(
                family="Corvidae",
                order_name="Passeriformes",
                detection_count=75,
                species_count=3,
                avg_confidence=0.82,
                latest_detection="2024-01-19T17:00:00",
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.get_family_summary(
            language_code="en", since=datetime(2024, 1, 1)
        )

        # Verify
        assert len(result) == 2
        assert result[0]["family"] == "Turdidae"
        assert result[0]["species_count"] == 5
        assert result[1]["family"] == "Corvidae"


class TestCountingMethods:
    """Test counting and aggregation methods."""

    @pytest.mark.asyncio
    async def test_get_species_counts(self, detection_query_service, mock_core_database):
        """Should get species counts for time range."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock rows with species counts - need to be directly iterable
        mock_rows = [
            MagicMock(scientific_name="Species1", common_name="Bird 1", count=25),
            MagicMock(scientific_name="Species2", common_name="Bird 2", count=15),
        ]

        # Mock result to be directly iterable
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)
        result = await detection_query_service.get_species_counts(start, end)

        # Verify
        assert len(result) == 2
        assert result[0]["scientific_name"] == "Species1"
        assert result[0]["count"] == 25

    @pytest.mark.asyncio
    async def test_get_hourly_counts(self, detection_query_service, mock_core_database):
        """Should get hourly detection counts."""
        import datetime as dt_module

        # Setup mock
        mock_session = AsyncMock()

        # Mock hourly data - needs to be directly iterable
        mock_rows = [
            MagicMock(hour=6, count=10),
            MagicMock(hour=7, count=15),
            MagicMock(hour=8, count=20),
        ]

        # Mock result to be directly iterable
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        target_date = dt_module.date(2024, 1, 15)
        result = await detection_query_service.get_hourly_counts(target_date)

        # Verify
        assert len(result) == 3
        assert result[0]["hour"] == 6
        assert result[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_count_by_species_with_filters(self, detection_query_service, mock_core_database):
        """Should count detections by species with date filters."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock species count results - needs to be dict-like iterable
        mock_rows = [
            {"scientific_name": "Species1", "count": 100},
            {"scientific_name": "Species2", "count": 75},
            {"scientific_name": "Species3", "count": 50},
        ]

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute - count_by_species doesn't accept min_confidence
        result = await detection_query_service.count_by_species(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )

        # Verify - count_by_species returns a dict
        assert len(result) == 3
        assert result["Species1"] == 100
        assert result["Species2"] == 75

    @pytest.mark.asyncio
    async def test_count_by_date(self, detection_query_service, mock_core_database):
        """Should count detections by date."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock date count results - needs to be dict-like iterable
        from datetime import date

        date1 = date(2024, 1, 15)
        date2 = date(2024, 1, 16)
        date3 = date(2024, 1, 17)
        mock_rows = [
            {"date": date1, "count": 50},
            {"date": date2, "count": 60},
            {"date": date3, "count": 45},
        ]

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_rows)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.count_by_date(species="Turdus migratorius")

        # Verify
        assert len(result) == 3
        assert result[date1] == 50
        assert result[date2] == 60
        assert result[date3] == 45


class TestAdvancedQueries:
    """Test advanced query methods."""

    @pytest.mark.asyncio
    async def test_get_species_counts_by_period(self, detection_query_service, mock_core_database):
        """Should get species counts grouped by time period."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock periodic counts
        mock_rows = [
            MagicMock(
                period="2024-01",
                scientific_name="Species1",
                common_name="Bird 1",
                count=150,
            ),
            MagicMock(
                period="2024-01",
                scientific_name="Species2",
                common_name="Bird 2",
                count=100,
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute - uses temporal_resolution not period, no min_confidence
        result = await detection_query_service.get_species_counts_by_period(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            temporal_resolution="daily",  # "hourly", "daily", or "weekly"
        )

        # Verify - returns list of dicts
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_detections_for_accumulation(
        self, detection_query_service, mock_core_database
    ):
        """Should get detections for species accumulation curve."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock detection results
        mock_rows = [
            MagicMock(
                timestamp="2024-01-15T10:00:00",
                scientific_name="Species1",
                common_name="Bird 1",
            ),
            MagicMock(
                timestamp="2024-01-15T11:00:00",
                scientific_name="Species2",
                common_name="Bird 2",
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute - only accepts start_date and end_date
        result = await detection_query_service.get_detections_for_accumulation(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )

        # Verify - returns list of tuples (from result.all())
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_species_counts_for_periods(
        self, detection_query_service, mock_core_database
    ):
        """Should get species counts for multiple time periods."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock periodic species counts
        mock_rows = [
            MagicMock(
                period_label="Morning",
                scientific_name="Species1",
                common_name="Bird 1",
                count=25,
            ),
            MagicMock(
                period_label="Evening",
                scientific_name="Species2",
                common_name="Bird 2",
                count=15,
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Define time periods - should be list of (start, end) tuples only
        periods = [
            (datetime(2024, 1, 1, 6, 0), datetime(2024, 1, 1, 12, 0)),
            (datetime(2024, 1, 1, 18, 0), datetime(2024, 1, 1, 23, 59)),
        ]

        # Execute - only accepts periods parameter
        result = await detection_query_service.get_species_counts_for_periods(periods)

        # Verify - returns list of dicts mapping species to counts
        assert len(result) == 2  # One dict per period
        assert isinstance(result[0], dict)

    @pytest.mark.asyncio
    async def test_get_species_sets_by_window(self, detection_query_service, mock_core_database):
        """Should get unique species sets by time window."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock window results
        mock_rows = [
            MagicMock(window="2024-01-15", species_list="Species1,Species2,Species3"),
            MagicMock(window="2024-01-16", species_list="Species1,Species2"),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute - takes window_size as timedelta, not window_type
        from datetime import timedelta

        result = await detection_query_service.get_species_sets_by_window(
            start_date=datetime(2024, 1, 15),
            end_date=datetime(2024, 1, 16),
            window_size=timedelta(days=1),
        )

        # Verify - returns list of dicts with period_start, period_end, species
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_weather_correlations(self, detection_query_service, mock_core_database):
        """Should get weather correlations with detections."""
        # Setup mock
        mock_session = AsyncMock()

        # Mock correlation results
        mock_rows = [
            MagicMock(
                hour=6,
                detection_count=10,
                avg_temperature=15.5,
                avg_humidity=65.0,
                avg_pressure=1013.25,
                avg_wind_speed=5.2,
            ),
            MagicMock(
                hour=7,
                detection_count=15,
                avg_temperature=16.2,
                avg_humidity=62.0,
                avg_pressure=1013.5,
                avg_wind_speed=4.8,
            ),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute - only accepts start_date and end_date
        result = await detection_query_service.get_weather_correlations(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )

        # Verify - returns dict not list
        assert isinstance(result, dict)


class TestErrorHandling:
    """Test error handling in query methods."""

    @pytest.mark.asyncio
    async def test_database_error_handling(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should handle database errors gracefully."""
        # Setup mock to raise error
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("Database connection failed")
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Should raise the error
        with pytest.raises(SQLAlchemyError):
            await detection_query_service.get_detections_with_taxa()

        # Ensure cleanup happens
        mock_species_database.detach_all_from_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_cleanup_on_error(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should ensure cleanup happens even on error."""
        # Setup mock to raise SQLAlchemyError during execution
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("Database error", "", "")
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Should raise the error
        with pytest.raises(SQLAlchemyError):
            await detection_query_service.get_detections_with_taxa(
                language_code="en",
                limit=10,
                offset=0,
            )

        # Ensure cleanup happens - detach_all_from_session should be called
        assert mock_species_database.detach_all_from_session.called


class TestHelperMethods:
    """Test helper and utility methods."""

    def test_build_where_clause_and_params(self, detection_query_service):
        """Should build WHERE clause with parameters."""
        # Required positional arguments first
        clause, params = detection_query_service._build_where_clause_and_params(
            "en",  # language_code
            100,  # limit
            0,  # offset
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            scientific_name_filter="Turdus migratorius",
            family_filter="Turdidae",
            genus_filter="Turdus",
            min_confidence=0.7,
            max_confidence=0.95,
        )

        # Check that clause has placeholders
        assert ":start_date" in clause or "start_date" in str(params)
        assert ":end_date" in clause or "end_date" in str(params)
        assert "confidence" in clause

        # Check params dict
        assert "start_date" in params
        assert "end_date" in params
        assert params["min_confidence"] == 0.7
        assert params["max_confidence"] == 0.95

    def test_build_where_clause_and_params_with_list(self, detection_query_service):
        """Should handle list filters in WHERE clause."""
        species_list = ["Species1", "Species2", "Species3"]
        # Required positional arguments first
        clause, params = detection_query_service._build_where_clause_and_params(
            "en",  # language_code
            100,  # limit
            0,  # offset
            scientific_name_filter=species_list,
        )

        # Should have IN clause
        assert "IN" in clause
        # Check params for species
        assert any("species" in str(k) for k in params.keys())

    def test_build_where_clause_and_params_empty(self, detection_query_service):
        """Should return WHERE 1=1 for empty filters."""
        # Required positional arguments
        clause, params = detection_query_service._build_where_clause_and_params(
            "en",  # language_code
            100,  # limit
            0,  # offset
        )
        assert "WHERE 1=1" in clause
        assert "language_code" in params
        assert params["language_code"] == "en"

    def test_build_order_clause_default(self, detection_query_service):
        """Should build default order clause."""
        clause = detection_query_service._build_order_clause()
        assert "timestamp" in clause.lower()
        assert "desc" in clause.lower()


class TestFilterBuilding:
    """Test filter building for count operations."""

    @pytest.mark.asyncio
    async def test_count_detections_with_complex_filters(
        self, detection_query_service, mock_core_database
    ):
        """Should handle complex filter combinations in count_detections."""
        # Setup mock
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=250)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Test with multiple filter types
        filters = {
            "species": ["Species1", "Species2"],
            "start_date": datetime(2024, 1, 1),
            "end_date": datetime(2024, 1, 31),
            "min_confidence": 0.6,
            "max_confidence": 0.95,
            "family": "Turdidae",
            "genus": "Turdus",
        }

        count = await detection_query_service.count_detections(filters)

        # Verify
        assert count == 250
        mock_session.scalar.assert_called_once()

        # Check that query was built with filters
        call_args = mock_session.scalar.call_args
        stmt = call_args[0][0]
        query_str = str(stmt)

        # Should contain filter references
        assert "WHERE" in query_str


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_parse_timestamp_with_invalid_string(self, detection_query_service):
        """Should handle invalid timestamp strings."""
        # This should raise an error
        with pytest.raises(ValueError):
            detection_query_service._parse_timestamp("not-a-timestamp")

    @pytest.mark.asyncio
    async def test_empty_result_sets(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should handle empty result sets properly."""
        # Setup mock with empty results
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        result = await detection_query_service.get_detections_with_taxa()

        # Should return empty list, not None
        assert result == []
        assert not result

    @pytest.mark.asyncio
    async def test_large_limit_values(
        self, detection_query_service, mock_core_database, mock_species_database
    ):
        """Should handle large limit values."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Test with very large limit
        result = await detection_query_service.get_detections_with_taxa(
            limit=1000000,
            offset=0,
        )

        # Should handle without error
        assert result == []

    def test_build_order_clause_variations(self, detection_query_service):
        """Should build different order clauses."""
        # Test ascending order
        asc_clause = detection_query_service._build_order_clause("confidence", False)
        assert "confidence" in asc_clause
        assert "ASC" in asc_clause

        # Test descending order
        desc_clause = detection_query_service._build_order_clause("timestamp", True)
        assert "timestamp" in desc_clause
        assert "DESC" in desc_clause
