"""Simple tests for DetectionQueryService that actually work."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_core_database(db_service_factory):
    """Mock core database."""
    mock, _session, _result = db_service_factory()
    return mock


@pytest.fixture
def mock_species_database():
    """Mock species database."""
    mock = MagicMock(spec=SpeciesDatabaseService)
    return mock


@pytest.fixture
def detection_query_service(mock_core_database, mock_species_database, test_config):
    """Create DetectionQueryService with mocks."""
    return DetectionQueryService(
        core_database=mock_core_database, species_database=mock_species_database, config=test_config
    )


class TestDetectionQueryServiceBasics:
    """Test basic DetectionQueryService functionality."""

    def test_parse_timestamp_datetime(self, detection_query_service):
        """Should parsing datetime objects."""
        now = datetime.now(UTC)
        result = detection_query_service._parse_timestamp(now)
        assert result == now

    def test_parse_timestamp_string(self, detection_query_service):
        """Should parsing ISO string timestamps."""
        timestamp_str = "2024-01-15T10:30:00"
        result = detection_query_service._parse_timestamp(timestamp_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_timestamp_invalid(self, detection_query_service):
        """Should handle invalid timestamp formats."""
        with pytest.raises(ValueError):
            detection_query_service._parse_timestamp("invalid-date")

    def test_apply_species_filter_single(self, detection_query_service):
        """Should applying single species filter."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_species_filter(stmt, "Turdus migratorius")
        assert str(filtered) != str(stmt)
        assert "scientific_name" in str(filtered).lower()

    def test_apply_species_filter_list(self, detection_query_service):
        """Should applying multiple species filter."""
        stmt = select(Detection)
        species_list = ["Turdus migratorius", "Cyanocitta cristata"]
        filtered = detection_query_service._apply_species_filter(stmt, species_list)
        assert str(filtered) != str(stmt)
        assert "scientific_name" in str(filtered).lower()

    def test_apply_species_filter_none(self, detection_query_service):
        """Should no filter when species is None."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_species_filter(stmt, None)
        assert filtered == stmt

    def test_apply_ordering(self, detection_query_service):
        """Should applying order by clause."""
        stmt = select(Detection)
        ordered = detection_query_service._apply_ordering(stmt, "timestamp", True)
        assert str(ordered) != str(stmt)
        assert "ORDER BY" in str(ordered)

    def test_build_order_clause(self, detection_query_service):
        """Should building SQL order clause."""
        clause = detection_query_service._build_order_clause()
        assert "timestamp" in clause
        assert "DESC" in clause
        clause = detection_query_service._build_order_clause("confidence", False)
        assert "confidence" in clause
        assert "ASC" in clause

    @pytest.mark.asyncio
    async def test_get_detection_count(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should counting detections in time range."""
        service, session, _ = db_service_factory(session_config={"scalar_result": 42})
        mock_core_database.get_async_db = service.get_async_db
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC)
        count = await detection_query_service.get_detection_count(start, end)
        assert count == 42
        session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unique_species_count(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should counting unique species."""
        service, session, _ = db_service_factory(session_config={"scalar_result": 25})
        mock_core_database.get_async_db = service.get_async_db
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)
        count = await detection_query_service.get_unique_species_count(start, end)
        assert count == 25
        session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_by_species(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should count detections by species."""
        mock_result = [
            {"scientific_name": "Turdus migratorius", "count": 100},
            {"scientific_name": "Cyanocitta cristata", "count": 50},
        ]
        service, _session, result = db_service_factory()
        result.__iter__ = lambda self: iter(mock_result)
        mock_core_database.get_async_db = service.get_async_db
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC)
        counts = await detection_query_service.count_by_species(start, end)
        assert counts == {"Turdus migratorius": 100, "Cyanocitta cristata": 50}

    @pytest.mark.asyncio
    async def test_count_by_date(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should count detections by date."""
        # SQLite's date() function returns ISO date strings, not date objects
        mock_result = [("2024-01-15", 75), ("2024-01-16", 60)]
        service, _session, _ = db_service_factory(session_config={"fetch_results": mock_result})
        mock_core_database.get_async_db = service.get_async_db
        counts = await detection_query_service.count_by_date("Turdus migratorius")
        # Function returns dict with string keys (ISO date format)
        assert counts == {"2024-01-15": 75, "2024-01-16": 60}

    @pytest.mark.asyncio
    async def test_get_storage_metrics(
        self, detection_query_service, mock_core_database, db_service_factory, row_factory
    ):
        """Should getting storage metrics."""
        mock_rows = row_factory([{"total_bytes": 1073741824, "total_duration": 7200.0}])
        # Override __bool__ to make row truthy (Row spec makes empty rows falsy)
        type(mock_rows[0]).__bool__ = lambda self: True
        service, _session, result = db_service_factory()
        result.first.return_value = mock_rows[0]
        mock_core_database.get_async_db = service.get_async_db
        metrics = await detection_query_service.get_storage_metrics()
        assert "total_bytes" in metrics
        assert "total_duration" in metrics
        assert metrics["total_bytes"] == 1073741824
        assert metrics["total_duration"] == 7200.0

    @pytest.mark.asyncio
    async def test_get_storage_metrics_no_data(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should handle no storage data."""
        service, _session, result = db_service_factory()
        result.first.return_value = None
        mock_core_database.get_async_db = service.get_async_db
        metrics = await detection_query_service.get_storage_metrics()
        assert metrics == {"total_bytes": 0, "total_duration": 0}

    @pytest.mark.asyncio
    async def test_count_detections(
        self, detection_query_service, mock_core_database, db_service_factory
    ):
        """Should counting detections with filters."""
        service, session, _ = db_service_factory(session_config={"scalar_result": 150})
        mock_core_database.get_async_db = service.get_async_db
        count = await detection_query_service.count_detections(
            {"species": "Turdus migratorius", "min_confidence": 0.7}
        )
        assert count == 150
        session.scalar.assert_called_once()
