"""Simple tests for DetectionQueryService that actually work."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_core_database():
    """Mock core database."""
    mock = MagicMock(spec=CoreDatabaseService)
    mock.get_async_db = MagicMock()  # Returns context manager
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
        core_database=mock_core_database,
        species_database=mock_species_database,
        config=test_config,
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
        # Invalid string format should raise ValueError
        with pytest.raises(ValueError):
            detection_query_service._parse_timestamp("invalid-date")

    def test_apply_species_filter_single(self, detection_query_service):
        """Should applying single species filter."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_species_filter(stmt, "Turdus migratorius")

        # Should add a WHERE clause
        assert str(filtered) != str(stmt)
        assert "scientific_name" in str(filtered).lower()

    def test_apply_species_filter_list(self, detection_query_service):
        """Should applying multiple species filter."""
        stmt = select(Detection)
        species_list = ["Turdus migratorius", "Cyanocitta cristata"]
        filtered = detection_query_service._apply_species_filter(stmt, species_list)

        # Should add WHERE with IN clause
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

        # Should add ORDER BY clause
        assert str(ordered) != str(stmt)
        assert "ORDER BY" in str(ordered)

    def test_build_order_clause(self, detection_query_service):
        """Should building SQL order clause."""
        # Test default ordering
        clause = detection_query_service._build_order_clause()
        assert "timestamp" in clause
        assert "DESC" in clause

        # Test custom ordering
        clause = detection_query_service._build_order_clause("confidence", False)
        assert "confidence" in clause
        assert "ASC" in clause

    @pytest.mark.asyncio
    async def test_get_detection_count(self, detection_query_service, mock_core_database):
        """Should counting detections in time range."""
        # Setup mock
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=42)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC)
        count = await detection_query_service.get_detection_count(start, end)

        # Verify
        assert count == 42
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unique_species_count(self, detection_query_service, mock_core_database):
        """Should counting unique species."""
        # Setup mock
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=25)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        start = datetime.now(UTC) - timedelta(days=7)
        end = datetime.now(UTC)
        count = await detection_query_service.get_unique_species_count(start, end)

        # Verify
        assert count == 25
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_by_species(self, detection_query_service, mock_core_database):
        """Should count detections by species."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = [
            {"scientific_name": "Turdus migratorius", "count": 100},
            {"scientific_name": "Cyanocitta cristata", "count": 50},
        ]
        # Mock the result object to be iterable
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = lambda self: iter(mock_result)
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC)
        counts = await detection_query_service.count_by_species(start, end)

        # Verify
        assert counts == {"Turdus migratorius": 100, "Cyanocitta cristata": 50}

    @pytest.mark.asyncio
    async def test_count_by_date(self, detection_query_service, mock_core_database):
        """Should count detections by date."""
        # Setup mock
        mock_session = AsyncMock()
        mock_date1 = datetime(2024, 1, 15).date()
        mock_date2 = datetime(2024, 1, 16).date()
        mock_result = [
            {"date": mock_date1, "count": 75},
            {"date": mock_date2, "count": 60},
        ]
        # Mock the result object to be iterable
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = lambda self: iter(mock_result)
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        counts = await detection_query_service.count_by_date("Turdus migratorius")

        # Verify
        assert counts == {mock_date1: 75, mock_date2: 60}

    @pytest.mark.asyncio
    async def test_get_storage_metrics(self, detection_query_service, mock_core_database):
        """Should getting storage metrics."""
        # Setup mock
        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.total_bytes = 1073741824  # 1GB
        mock_row.total_duration = 7200.0  # 2 hours
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        metrics = await detection_query_service.get_storage_metrics()

        # Verify - only has total_bytes and total_duration
        assert "total_bytes" in metrics
        assert "total_duration" in metrics
        assert metrics["total_bytes"] == 1073741824
        assert metrics["total_duration"] == 7200.0

    @pytest.mark.asyncio
    async def test_get_storage_metrics_no_data(self, detection_query_service, mock_core_database):
        """Should handle no storage data."""
        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None  # No data
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute
        metrics = await detection_query_service.get_storage_metrics()

        # Verify - returns empty dict or default values
        assert metrics == {"total_bytes": 0, "total_duration": 0}

    @pytest.mark.asyncio
    async def test_count_detections(self, detection_query_service, mock_core_database):
        """Should counting detections with filters."""
        # Setup mock
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=150)
        mock_core_database.get_async_db.return_value.__aenter__.return_value = mock_session

        # Execute with filters
        count = await detection_query_service.count_detections(
            {"species": "Turdus migratorius", "min_confidence": 0.7}
        )

        # Verify
        assert count == 150
        mock_session.scalar.assert_called_once()
