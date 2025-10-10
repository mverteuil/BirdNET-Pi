"""Refactored timestamp parsing tests with parameterization."""

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
    """Test basic DetectionQueryService functionality with parameterized tests."""

    @pytest.mark.parametrize(
        "input_value,expected_type,expected_attributes",
        [
            pytest.param(
                datetime.now(UTC),
                datetime,
                None,  # Already a datetime, no attributes to check
                id="datetime_passthrough",
            ),
            pytest.param(
                "2024-01-15T10:30:00",
                datetime,
                {"year": 2024, "month": 1, "day": 15, "hour": 10, "minute": 30},
                id="iso_string_standard",
            ),
            pytest.param(
                "2024-12-31T23:59:59",
                datetime,
                {"year": 2024, "month": 12, "day": 31, "hour": 23, "minute": 59, "second": 59},
                id="iso_string_endofyear",
            ),
            pytest.param(
                "2024-02-29T00:00:00",  # Leap year
                datetime,
                {"year": 2024, "month": 2, "day": 29},
                id="iso_string_leapyear",
            ),
        ],
    )
    def test_parse_timestamp_valid(
        self, detection_query_service, input_value, expected_type, expected_attributes
    ):
        """Should parse valid timestamp formats correctly."""
        result = detection_query_service._parse_timestamp(input_value)

        assert isinstance(result, expected_type)

        if expected_attributes:
            for attr, expected_val in expected_attributes.items():
                assert getattr(result, attr) == expected_val

    @pytest.mark.parametrize(
        "invalid_input,error_message",
        [
            pytest.param("invalid-date", "Invalid", id="invalid_format"),
            pytest.param("2024-13-01T00:00:00", "month", id="invalid_month"),
            pytest.param("2024-02-30T00:00:00", "day", id="invalid_day"),
            pytest.param("", "empty", id="empty_string"),
            pytest.param(None, "None", id="none_value"),
            pytest.param(12345, "integer", id="integer_input"),
        ],
    )
    def test_parse_timestamp_invalid(self, detection_query_service, invalid_input, error_message):
        """Should raise ValueError for invalid timestamp: {error_message}."""
        with pytest.raises(ValueError):
            detection_query_service._parse_timestamp(invalid_input)


class TestSpeciesFiltering:
    """Test species filtering with parameterization."""

    @pytest.mark.parametrize(
        "species_filter,expected_in_query",
        [
            pytest.param(
                "Turdus migratorius",
                "scientific_name",
                id="single_species",
            ),
            pytest.param(
                ["Turdus migratorius", "Cyanocitta cristata"],
                "scientific_name",
                id="multiple_species",
            ),
            pytest.param(
                None,
                None,  # No filter should be applied
                id="no_filter",
            ),
            pytest.param(
                [],
                None,  # Empty list should apply no filter
                id="empty_list",
            ),
        ],
    )
    def test_apply_species_filter(self, detection_query_service, species_filter, expected_in_query):
        """Should apply species filter correctly for different input types."""
        stmt = select(Detection)
        filtered = detection_query_service._apply_species_filter(stmt, species_filter)

        if expected_in_query:
            assert str(filtered) != str(stmt)
            assert expected_in_query in str(filtered).lower()
        else:
            assert filtered == stmt  # No change expected


class TestOrderingAndPagination:
    """Test query ordering and pagination with parameterization."""

    @pytest.mark.parametrize(
        "order_by,desc,expected_clause",
        [
            pytest.param("timestamp", True, "timestamp DESC", id="timestamp_desc"),
            pytest.param("timestamp", False, "timestamp ASC", id="timestamp_asc"),
            pytest.param("confidence", True, "confidence DESC", id="confidence_desc"),
            pytest.param("confidence", False, "confidence ASC", id="confidence_asc"),
            pytest.param("scientific_name", True, "scientific_name DESC", id="species_desc"),
            pytest.param(None, None, "timestamp DESC", id="default_ordering"),  # Default behavior
        ],
    )
    def test_build_order_clause(self, detection_query_service, order_by, desc, expected_clause):
        """Should build correct SQL order clause for different parameters."""
        if order_by is None:
            clause = detection_query_service._build_order_clause()
        else:
            clause = detection_query_service._build_order_clause(order_by, desc)

        assert expected_clause in clause


# Example of using fixture parameterization for complex test setups
class TestCountingOperations:
    """Test various counting operations with fixture parameterization."""

    @pytest.fixture(
        params=[
            {"scalar_result": 0, "description": "no detections"},
            {"scalar_result": 42, "description": "some detections"},
            {"scalar_result": 1000, "description": "many detections"},
        ],
        ids=lambda p: p["description"],
    )
    def count_scenario(self, request, db_service_factory):
        """Provide different counting scenarios."""
        service, session, _ = db_service_factory(
            session_config={"scalar_result": request.param["scalar_result"]}
        )
        return service, session, request.param

    @pytest.mark.asyncio
    async def test_get_detection_count_scenarios(
        self, detection_query_service, mock_core_database, count_scenario
    ):
        """Should handle different detection count scenarios correctly."""
        service, _session, scenario = count_scenario
        mock_core_database.get_async_db = service.get_async_db

        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC)

        count = await detection_query_service.get_detection_count(start, end)

        expected = scenario["scalar_result"] if scenario["scalar_result"] is not None else 0
        assert count == expected
