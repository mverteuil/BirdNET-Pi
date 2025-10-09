"""Comprehensive tests for DetectionQueryService to improve coverage."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection, DetectionWithTaxa
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_core_database(db_service_factory):
    """Mock core database."""
    mock, _session, _result = db_service_factory()
    return mock


@pytest.fixture
def mock_species_database():
    """Mock species database."""
    mock = MagicMock(
        spec=SpeciesDatabaseService,
        attach_all_to_session=AsyncMock(spec=callable),
        detach_all_from_session=AsyncMock(spec=callable),
    )
    return mock


@pytest.fixture
def detection_query_service(mock_core_database, mock_species_database, test_config):
    """Create DetectionQueryService with mocks."""
    return DetectionQueryService(
        core_database=mock_core_database, species_database=mock_species_database, config=test_config
    )


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
        stmt = select(Detection)
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        filtered = detection_query_service._apply_date_filters(stmt, start, end)
        query_str = str(filtered)
        assert "timestamp >=" in query_str
        assert "timestamp <=" in query_str

    def test_apply_date_filters_start_only(self, detection_query_service):
        """Should apply only start date filter."""
        stmt = select(Detection)
        start = datetime(2024, 1, 1)
        filtered = detection_query_service._apply_date_filters(stmt, start, None)
        assert "timestamp >=" in str(filtered)
        assert "timestamp <=" not in str(filtered)

    def test_apply_date_filters_end_only(self, detection_query_service):
        """Should apply only end date filter."""
        stmt = select(Detection)
        end = datetime(2024, 1, 31)
        filtered = detection_query_service._apply_date_filters(stmt, None, end)
        assert "timestamp <=" in str(filtered)
        assert "timestamp >=" not in str(filtered)

    def test_apply_confidence_filters_both(self, detection_query_service):
        """Should apply both min and max confidence filters."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, 0.5, 0.9)
        query_str = str(filtered)
        assert "confidence >=" in query_str
        assert "confidence <=" in query_str

    def test_apply_confidence_filters_min_only(self, detection_query_service):
        """Should apply only min confidence filter."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, 0.5, None)
        assert "confidence >=" in str(filtered)

    def test_apply_confidence_filters_max_only(self, detection_query_service):
        """Should apply only max confidence filter."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_confidence_filters(stmt, None, 0.9)
        assert "confidence <=" in str(filtered)

    def test_apply_ordering_default_column(self, detection_query_service):
        """Should use default column when invalid order_by specified."""
        stmt = select(Detection)
        ordered = detection_query_service._apply_ordering(stmt, "invalid_column", True)
        assert "ORDER BY" in str(ordered)

    def test_apply_ordering_ascending(self, detection_query_service):
        """Should apply ascending order."""
        stmt = select(Detection)
        ordered = detection_query_service._apply_ordering(stmt, "confidence", False)
        query_str = str(ordered)
        assert "ORDER BY" in query_str
        assert "DESC" not in query_str


class TestMainQueryMethods:
    """Test main query methods."""

    @pytest.mark.asyncio
    async def test_query_detections_delegates(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should delegate to _execute_join_query."""
        service, session, _ = db_service_factory(session_config={"fetch_results": []})
        mock_core_database.get_async_db = service.get_async_db
        with patch.object(
            detection_query_service, "_execute_join_query", new_callable=AsyncMock
        ) as mock_method:
            mock_method.return_value = []
            await detection_query_service.query_detections(
                species="Turdus migratorius", family="Turdidae", genus="Turdus", min_confidence=0.7
            )
            mock_method.assert_called_once_with(
                session=session,
                limit=None,
                offset=0,
                start_date=None,
                end_date=None,
                scientific_name_filter="Turdus migratorius",
                family_filter="Turdidae",
                genus_filter="Turdus",
                min_confidence=0.7,
                max_confidence=None,
                order_by="timestamp",
                order_desc=True,
                include_first_detections=False,
            )

    @pytest.mark.asyncio
    async def test_get_detections_with_taxa_legacy_since(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should support legacy 'since' parameter."""
        service, session, _ = db_service_factory(session_config={"mappings_result": []})
        mock_core_database.get_async_db = service.get_async_db
        since_date = datetime(2024, 1, 1)
        result = await detection_query_service.get_detections_with_taxa(since=since_date)
        session.execute.assert_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_detections_with_taxa_full_filters(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should apply all filters in get_detections_with_taxa."""
        service, session, _ = db_service_factory(session_config={"mappings_result": []})
        mock_core_database.get_async_db = service.get_async_db
        await detection_query_service.get_detections_with_taxa(
            limit=50,
            offset=10,
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
        session.execute.assert_called()
        mock_species_database.attach_all_to_session.assert_called()
        mock_species_database.detach_all_from_session.assert_called()

    @pytest.mark.asyncio
    async def test_get_detection_with_taxa_found(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should return detection with taxa when found."""
        detection_id = uuid4()
        mock_row = SimpleNamespace(
            id=str(detection_id),
            species_tensor="tensor",
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.9,
            timestamp="2024-01-15T10:30:00",
            audio_file_id=str(uuid4()),
            latitude=45.5,
            longitude=-73.6,
            species_confidence_threshold=0.7,
            week=3,
            sensitivity_setting=1.5,
            overlap=2.0,
            ioc_english_name="American Robin",
            translated_name="Merle d'Amérique",
            family="Turdidae",
            genus="Turdus",
            order_name="Passeriformes",
        )
        service, _session, mock_result = db_service_factory()
        mock_result.fetchone.return_value = mock_row
        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_detection_with_taxa(detection_id)
        assert result is not None
        assert isinstance(result, DetectionWithTaxa)
        assert result.family == "Turdidae"
        assert result.genus == "Turdus"
        assert result.order_name == "Passeriformes"

    @pytest.mark.asyncio
    async def test_get_detection_with_taxa_not_found(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should return None when detection not found."""
        service, _session, mock_result = db_service_factory()
        mock_result.fetchone.return_value = None
        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_detection_with_taxa(uuid4())
        assert result is None


class TestSummaryMethods:
    """Test summary and aggregation methods."""

    @pytest.mark.asyncio
    async def test_get_species_summary(
        self,
        detection_query_service,
        mock_core_database,
        mock_species_database,
        row_factory,
        db_service_factory,
    ):
        """Should get species summary with counts."""
        mock_rows = row_factory(
            [
                {
                    "scientific_name": "Species1",
                    "detection_count": 50,
                    "avg_confidence": 0.75,
                    "latest_detection": "2024-01-15T16:00:00",
                    "ioc_english_name": "Bird 1",
                    "translated_name": "Oiseau 1",
                    "family": "Turdidae",
                    "genus": "Turdus",
                    "order_name": "Passeriformes",
                },
                {
                    "scientific_name": "Species2",
                    "detection_count": 30,
                    "avg_confidence": 0.8,
                    "latest_detection": "2024-01-14T17:00:00",
                    "ioc_english_name": "Bird 2",
                    "translated_name": "Oiseau 2",
                    "family": "Turdidae",
                    "genus": "Turdus",
                    "order_name": "Passeriformes",
                },
            ]
        )
        service, _session, _ = db_service_factory(session_config={"fetch_results": mock_rows})
        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_species_summary(
            since=datetime(2024, 1, 1), family_filter="Turdidae"
        )
        assert len(result) == 2
        assert result[0]["scientific_name"] == "Species1"
        assert result[0]["detection_count"] == 50
        assert result[1]["scientific_name"] == "Species2"

    @pytest.mark.asyncio
    async def test_get_family_summary(
        self,
        detection_query_service,
        mock_core_database,
        mock_species_database,
        row_factory,
        db_service_factory,
    ):
        """Should get family summary with counts."""
        mock_rows = row_factory(
            [
                {
                    "family": "Turdidae",
                    "order_name": "Passeriformes",
                    "detection_count": 100,
                    "species_count": 5,
                    "avg_confidence": 0.78,
                    "latest_detection": "2024-01-20T18:00:00",
                },
                {
                    "family": "Corvidae",
                    "order_name": "Passeriformes",
                    "detection_count": 75,
                    "species_count": 3,
                    "avg_confidence": 0.82,
                    "latest_detection": "2024-01-19T17:00:00",
                },
            ]
        )
        service, _session, _ = db_service_factory(session_config={"fetch_results": mock_rows})
        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_family_summary(since=datetime(2024, 1, 1))
        assert len(result) == 2
        assert result[0]["family"] == "Turdidae"
        assert result[0]["species_count"] == 5
        assert result[1]["family"] == "Corvidae"


class TestCountingMethods:
    """Test counting and aggregation methods."""

    @pytest.mark.asyncio
    async def test_get_species_counts(
        self, detection_query_service, mock_core_database, row_factory, db_service_factory
    ):
        """Should get species counts for time range."""
        mock_rows = row_factory(
            [
                {"scientific_name": "Species1", "common_name": "Bird 1", "count": 25},
                {"scientific_name": "Species2", "common_name": "Bird 2", "count": 15},
            ]
        )
        service, _session, result = db_service_factory()
        result.__iter__ = lambda self: iter(mock_rows)
        mock_core_database.get_async_db = service.get_async_db
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)
        result = await detection_query_service.get_species_counts(start, end)
        assert len(result) == 2
        assert result[0]["scientific_name"] == "Species1"
        assert result[0]["count"] == 25

    @pytest.mark.asyncio
    async def test_get_hourly_counts(
        self, detection_query_service, mock_core_database, row_factory, db_service_factory
    ):
        """Should get hourly detection counts."""
        mock_rows = row_factory(
            [
                {"hour": 6, "count": 10},
                {"hour": 7, "count": 15},
                {"hour": 8, "count": 20},
            ]
        )
        service, _session, result = db_service_factory()
        result.__iter__ = lambda self: iter(mock_rows)
        mock_core_database.get_async_db = service.get_async_db
        target_date = date(2024, 1, 15)
        result = await detection_query_service.get_hourly_counts(target_date)
        assert len(result) == 3
        assert result[0]["hour"] == 6
        assert result[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_count_by_species_with_filters(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should count detections by species with date filters."""
        service, _session, result = db_service_factory()

        mock_rows = [
            {"scientific_name": "Species1", "count": 100},
            {"scientific_name": "Species2", "count": 75},
            {"scientific_name": "Species3", "count": 50},
        ]

        result.__iter__ = lambda self: iter(mock_rows)

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.count_by_species(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        assert len(result) == 3
        assert result["Species1"] == 100
        assert result["Species2"] == 75

    @pytest.mark.asyncio
    async def test_count_by_date(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should count detections by date."""
        # SQLite's date() function returns ISO date strings, not date objects
        service, _session, _ = db_service_factory(
            session_config={
                "fetch_results": [
                    ("2024-01-15", 50),
                    ("2024-01-16", 60),
                    ("2024-01-17", 45),
                ]
            }
        )

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.count_by_date(species="Turdus migratorius")
        # Function returns dict with string keys (ISO date format)
        assert len(result) == 3
        assert result["2024-01-15"] == 50
        assert result["2024-01-16"] == 60
        assert result["2024-01-17"] == 45


class TestAdvancedQueries:
    """Test advanced query methods."""

    @pytest.mark.asyncio
    async def test_get_species_counts_by_period(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should get species counts grouped by time period."""
        service, _session, result = db_service_factory()
        mock_rows = [
            MagicMock(
                spec=Row,
                period="2024-01",
                scientific_name="Species1",
                common_name="Bird 1",
                count=150,
            ),
            MagicMock(
                spec=Row,
                period="2024-01",
                scientific_name="Species2",
                common_name="Bird 2",
                count=100,
            ),
        ]

        result.all.return_value = mock_rows

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_species_counts_by_period(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            temporal_resolution="daily",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_detections_for_accumulation(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should get detections for species accumulation curve."""
        service, _session, result = db_service_factory()
        mock_rows = [
            MagicMock(
                spec=Row,
                timestamp="2024-01-15T10:00:00",
                scientific_name="Species1",
                common_name="Bird 1",
            ),
            MagicMock(
                spec=Row,
                timestamp="2024-01-15T11:00:00",
                scientific_name="Species2",
                common_name="Bird 2",
            ),
        ]

        result.all.return_value = mock_rows

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_detections_for_accumulation(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_species_counts_for_periods(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should get species counts for multiple time periods."""
        service, _session, result = db_service_factory()
        mock_rows = [
            MagicMock(
                spec=Row,
                period_label="Morning",
                scientific_name="Species1",
                common_name="Bird 1",
                count=25,
            ),
            MagicMock(
                spec=Row,
                period_label="Evening",
                scientific_name="Species2",
                common_name="Bird 2",
                count=15,
            ),
        ]

        result.all.return_value = mock_rows

        mock_core_database.get_async_db = service.get_async_db
        periods = [
            (datetime(2024, 1, 1, 6, 0), datetime(2024, 1, 1, 12, 0)),
            (datetime(2024, 1, 1, 18, 0), datetime(2024, 1, 1, 23, 59)),
        ]
        result = await detection_query_service.get_species_counts_for_periods(periods)
        assert len(result) == 2
        assert isinstance(result[0], dict)

    @pytest.mark.asyncio
    async def test_get_species_sets_by_window(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should get unique species sets by time window."""
        service, _session, result = db_service_factory()
        mock_rows = [
            MagicMock(spec=Row, window="2024-01-15", species_list="Species1,Species2,Species3"),
            MagicMock(spec=Row, window="2024-01-16", species_list="Species1,Species2"),
        ]

        result.all.return_value = mock_rows

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_species_sets_by_window(
            start_date=datetime(2024, 1, 15),
            end_date=datetime(2024, 1, 16),
            window_size=timedelta(days=1),
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_weather_correlations(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should get weather correlations with detections."""
        service, _session, result = db_service_factory()
        mock_rows = [
            SimpleNamespace(
                hour=6,
                detection_count=10,
                species_count=5,
                temperature=15.5,
                humidity=65.0,
                pressure=1013.25,
                wind_speed=5.2,
                precipitation=0.0,
            ),
            SimpleNamespace(
                hour=7,
                detection_count=15,
                species_count=8,
                temperature=16.2,
                humidity=62.0,
                pressure=1013.5,
                wind_speed=4.8,
                precipitation=0.5,
            ),
        ]
        result.all.return_value = mock_rows
        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_weather_correlations(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        assert isinstance(result, dict)


class TestErrorHandling:
    """Test error handling in query methods."""

    @pytest.mark.asyncio
    async def test_database_error_handling(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should handle database errors gracefully."""
        service, _session, _ = db_service_factory(
            session_config={"side_effect": SQLAlchemyError("Database connection failed")}
        )

        mock_core_database.get_async_db = service.get_async_db
        with pytest.raises(SQLAlchemyError):
            await detection_query_service.get_detections_with_taxa()
        mock_species_database.detach_all_from_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_cleanup_on_error(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should ensure cleanup happens even on error."""
        service, _session, _ = db_service_factory(
            session_config={"side_effect": SQLAlchemyError("Database error", "", "")}
        )

        mock_core_database.get_async_db = service.get_async_db
        with pytest.raises(SQLAlchemyError):
            await detection_query_service.get_detections_with_taxa(limit=10, offset=0)
        assert mock_species_database.detach_all_from_session.called


class TestHelperMethods:
    """Test helper and utility methods."""

    def test_build_where_clause_and_params(self, detection_query_service):
        """Should build WHERE clause with parameters."""
        clause, params = detection_query_service._build_where_clause_and_params(
            100,
            0,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            scientific_name_filter="Turdus migratorius",
            family_filter="Turdidae",
            genus_filter="Turdus",
            min_confidence=0.7,
            max_confidence=0.95,
        )
        assert ":start_date" in clause or "start_date" in str(params)
        assert ":end_date" in clause or "end_date" in str(params)
        assert "confidence" in clause
        assert "start_date" in params
        assert "end_date" in params
        assert params["min_confidence"] == 0.7
        assert params["max_confidence"] == 0.95

    def test_build_where_clause_and_params_with_list(self, detection_query_service):
        """Should handle list filters in WHERE clause."""
        species_list = ["Species1", "Species2", "Species3"]
        clause, params = detection_query_service._build_where_clause_and_params(
            100, 0, scientific_name_filter=species_list
        )
        assert "IN" in clause
        assert any("species" in str(k) for k in params.keys())

    def test_build_where_clause_and_params_empty(self, detection_query_service):
        """Should return WHERE 1=1 for empty filters."""
        clause, params = detection_query_service._build_where_clause_and_params(100, 0)
        assert "WHERE 1=1" in clause
        assert "language_code" in params

    def test_build_order_clause_default(self, detection_query_service):
        """Should build default order clause."""
        clause = detection_query_service._build_order_clause()
        assert "timestamp" in clause.lower()
        assert "desc" in clause.lower()


class TestFilterBuilding:
    """Test filter building for count operations."""

    @pytest.mark.asyncio
    async def test_count_detections_with_complex_filters(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should handle complex filter combinations in count_detections."""
        service, session, _ = db_service_factory(session_config={"scalar_result": 250})

        mock_core_database.get_async_db = service.get_async_db
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
        assert count == 250
        session.scalar.assert_called_once()
        call_args = session.scalar.call_args
        stmt = call_args[0][0]
        query_str = str(stmt)
        assert "WHERE" in query_str


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_parse_timestamp_with_invalid_string(self, detection_query_service):
        """Should handle invalid timestamp strings."""
        with pytest.raises(ValueError):
            detection_query_service._parse_timestamp("not-a-timestamp")

    @pytest.mark.asyncio
    async def test_empty_result_sets(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should handle empty result sets properly."""
        service, _session, _ = db_service_factory(session_config={"mappings_result": []})

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_detections_with_taxa()
        assert result == []
        assert not result

    @pytest.mark.asyncio
    async def test_large_limit_values(
        self, detection_query_service, mock_core_database, mock_species_database, db_service_factory
    ):
        """Should handle large limit values."""
        service, _session, _ = db_service_factory(session_config={"mappings_result": []})

        mock_core_database.get_async_db = service.get_async_db
        result = await detection_query_service.get_detections_with_taxa(limit=1000000, offset=0)
        assert result == []

    def test_build_order_clause_variations(self, detection_query_service):
        """Should build different order clauses."""
        asc_clause = detection_query_service._build_order_clause("confidence", False)
        assert "confidence" in asc_clause
        assert "ASC" in asc_clause
        desc_clause = detection_query_service._build_order_clause("timestamp", True)
        assert "timestamp" in desc_clause
        assert "DESC" in desc_clause
