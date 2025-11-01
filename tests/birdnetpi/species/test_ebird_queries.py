"""Tests for eBird query service with neighbor search and confidence calculations."""

from collections import namedtuple

import pytest

from birdnetpi.config.models import EBirdFilterConfig
from birdnetpi.species.ebird_queries import EBirdQueryService


@pytest.fixture
def ebird_query_service():
    """Create eBird query service instance."""
    return EBirdQueryService()


@pytest.fixture
def mock_session_factory(db_session_factory):
    """Provide session factory for tests that need to configure results."""
    return db_session_factory


@pytest.fixture
def base_config():
    """Create base eBird filter configuration for tests."""
    return EBirdFilterConfig(
        enabled=True,
        h3_resolution=5,
        neighbor_search_enabled=True,
        neighbor_search_max_rings=2,
        neighbor_boost_decay_per_ring=0.15,
        quality_multiplier_base=0.7,
        quality_multiplier_range=0.3,
        use_monthly_frequency=True,
        absence_penalty_factor=0.8,
        peak_season_boost=1.0,
        off_season_penalty=1.0,
    )


class TestGetConfidenceWithNeighbors:
    """Test neighbor search with confidence calculation."""

    @pytest.mark.asyncio
    async def test_exact_match_no_neighbors(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should find species in exact cell without neighbor search."""
        # Create mock row with all required fields
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        # User cell: 852a1073fffffff (hex) = 599718752904282111 (int) - NYC at resolution 5
        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=0.8,
            scientific_name="Cyanocitta cristata",
            month_frequency=0.25,
            quarter_frequency=0.28,
            year_frequency=0.3,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,  # New York City
            longitude=-74.0060,
            config=base_config,
            month=6,
        )

        assert result_data is not None
        assert result_data["confidence_tier"] == "common"
        assert result_data["h3_cell"] == "852a1073fffffff"
        assert result_data["ring_distance"] == 0  # Exact match
        assert isinstance(result_data["confidence_boost"], float)
        assert result_data["region_pack"] is None

    @pytest.mark.asyncio
    async def test_neighbor_match_with_decay(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should find species in neighbor cell with distance decay applied."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        # Neighbor cell (different from user cell)
        species_row = MockRow(
            h3_cell=599718724986994687,  # Different cell
            confidence_tier="uncommon",
            base_boost=1.3,
            yearly_frequency=0.15,
            quality_score=0.6,
            scientific_name="Cyanocitta cristata",
            month_frequency=0.12,
            quarter_frequency=0.14,
            year_frequency=0.15,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=6,
        )

        assert result_data is not None
        assert result_data["ring_distance"] >= 0
        # Confidence boost should be positive
        assert result_data["confidence_boost"] > 0

    @pytest.mark.asyncio
    async def test_no_match_in_any_ring(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should return None when species not found in any searched ring."""
        session, _result = mock_session_factory(fetch_results=[])  # No matches

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Nonexistent species",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=6,
        )

        assert result_data is None

    @pytest.mark.asyncio
    async def test_neighbor_search_disabled(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should only search exact cell when neighbor search disabled."""
        base_config.neighbor_search_enabled = False

        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=0.8,
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=None,
            year_frequency=None,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=None,
        )

        assert result_data is not None
        assert result_data["ring_distance"] == 0

    @pytest.mark.asyncio
    async def test_temporal_adjustments_with_month(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should apply temporal adjustments based on monthly frequency."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=0.8,
            scientific_name="Cyanocitta cristata",
            month_frequency=0.0,  # Absent in this month
            quarter_frequency=0.28,
            year_frequency=0.3,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=6,
        )

        assert result_data is not None
        # Absence penalty should be applied
        assert result_data["confidence_boost"] < 1.5  # Less than base boost

    @pytest.mark.asyncio
    async def test_temporal_adjustments_without_month(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should skip temporal adjustments when month not provided."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=0.8,
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=None,
            year_frequency=None,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=None,  # No month provided
        )

        assert result_data is not None
        # No temporal multiplier applied, only base x quality x ring
        assert result_data["confidence_boost"] > 0

    @pytest.mark.asyncio
    async def test_quality_multiplier_calculation(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should apply quality multiplier based on observation quality."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        # High quality score
        high_quality_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=1.0,  # Perfect quality
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=None,
            year_frequency=None,
        )

        session, _result = mock_session_factory(fetch_results=[high_quality_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=None,
        )

        assert result_data is not None
        # High quality should give full multiplier (0.7 + 0.3 * 1.0 = 1.0)
        expected_quality_mult = 0.7 + (0.3 * 1.0)
        assert abs(result_data["confidence_boost"] / 1.5 - expected_quality_mult) < 0.01


class TestConfidenceCalculationComponents:
    """Test individual components of confidence calculation."""

    @pytest.mark.asyncio
    async def test_ring_multiplier_calculation(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should calculate correct ring distance multiplier."""
        # Ring 0 (exact): 1.0
        # Ring 1: 1.0 - (1 * 0.15) = 0.85
        # Ring 2: 1.0 - (2 * 0.15) = 0.70

        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.0,  # Use 1.0 for easier calculation
            yearly_frequency=0.3,
            quality_score=0.5,  # Middle quality for 0.85 multiplier
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=None,
            year_frequency=None,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=None,
        )

        assert result_data is not None
        assert result_data["ring_distance"] == 0
        # Exact match: base (1.0) x ring (1.0) x quality (0.85) x temporal (1.0) = 0.85
        assert abs(result_data["confidence_boost"] - 0.85) < 0.01

    @pytest.mark.parametrize(
        "month,expected_quarter",
        [
            (1, 1),  # January -> Q1
            (3, 1),  # March -> Q1
            (4, 2),  # April -> Q2
            (6, 2),  # June -> Q2
            (7, 3),  # July -> Q3
            (9, 3),  # September -> Q3
            (10, 4),  # October -> Q4
            (12, 4),  # December -> Q4
        ],
    )
    @pytest.mark.asyncio
    async def test_quarter_calculation(
        self, ebird_query_service, mock_session_factory, base_config, month, expected_quarter
    ):
        """Should correctly calculate quarter from month."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=0.8,
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=0.25,
            year_frequency=0.3,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=month,
        )

        # Verify quarter parameter was passed correctly
        call_args = session.execute.call_args
        # Parameters are passed as the second positional argument (statement, params_dict)
        params = call_args[0][1]
        assert params["quarter"] == expected_quarter


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_missing_quality_score(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should use default quality score when missing."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="common",
            base_boost=1.5,
            yearly_frequency=0.3,
            quality_score=None,  # Missing
            scientific_name="Cyanocitta cristata",
            month_frequency=None,
            quarter_frequency=None,
            year_frequency=None,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Cyanocitta cristata",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=None,
        )

        assert result_data is not None
        # Should use default quality score (0.5)
        assert result_data["confidence_boost"] > 0

    @pytest.mark.asyncio
    async def test_zero_boost_not_returned(
        self, ebird_query_service, mock_session_factory, base_config
    ):
        """Should ensure confidence boost is always positive."""
        MockRow = namedtuple(
            "MockRow",
            [
                "h3_cell",
                "confidence_tier",
                "base_boost",
                "yearly_frequency",
                "quality_score",
                "scientific_name",
                "month_frequency",
                "quarter_frequency",
                "year_frequency",
            ],
        )

        species_row = MockRow(
            h3_cell=599718752904282111,
            confidence_tier="vagrant",
            base_boost=0.1,  # Very low boost
            yearly_frequency=0.01,
            quality_score=0.1,
            scientific_name="Rare species",
            month_frequency=0.0,  # Absent
            quarter_frequency=0.0,
            year_frequency=0.01,
        )

        session, _result = mock_session_factory(fetch_results=[species_row])

        result_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name="Rare species",
            latitude=40.7128,
            longitude=-74.0060,
            config=base_config,
            month=6,
        )

        assert result_data is not None
        assert result_data["confidence_boost"] > 0  # Should still be positive
