"""Refactored correlation test with parameterization."""

from unittest.mock import MagicMock

import pytest

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.detections.queries import DetectionQueryService


@pytest.fixture
def mock_detection_query_service():
    """Create a mock DetectionQueryService."""
    return MagicMock(spec=DetectionQueryService)


@pytest.fixture
def analytics_manager(mock_detection_query_service, test_config):
    """Create an AnalyticsManager with mocked dependencies."""
    return AnalyticsManager(mock_detection_query_service, test_config)


class TestDiversityMetrics:
    """Test biodiversity calculation methods."""

    @pytest.mark.parametrize(
        "x,y,expected_correlation,description",
        [
            pytest.param(
                [1, 2, 3, 4, 5],
                [2, 4, 6, 8, 10],
                1.0,
                "perfect positive correlation",
                id="perfect_positive",
            ),
            pytest.param(
                [1, 2, 3, 4, 5],
                [10, 8, 6, 4, 2],
                -1.0,
                "perfect negative correlation",
                id="perfect_negative",
            ),
            pytest.param(
                [1, 2, 3, 4, 5],
                [3, 3, 3, 3, 3],
                0.0,
                "no correlation (constant y)",
                id="no_correlation",
            ),
            pytest.param(
                [1, 2, 3, 4, 5],
                [1, 4, 2, 8, 5],
                0.7,  # Approximate correlation
                "moderate positive correlation",
                id="moderate_positive",
            ),
            pytest.param(
                [10, 20, 30, 40, 50],
                [50, 40, 30, 20, 10],
                -1.0,
                "perfect negative with larger values",
                id="perfect_negative_large",
            ),
        ],
    )
    def test_calculate_correlation(
        self, analytics_manager, x, y, expected_correlation, description
    ):
        """Should calculate correlation coefficients correctly for {description}."""
        correlation = analytics_manager.calculate_correlation(x, y)

        # Use appropriate tolerance based on expected value
        if expected_correlation == 0.0:
            assert correlation == pytest.approx(expected_correlation, abs=1e-5)
        else:
            assert correlation == pytest.approx(expected_correlation, rel=0.1)


# Alternative approach using indirect parametrization for complex data setup
class TestCorrelationWithComplexData:
    """Test correlation with more complex data patterns."""

    @pytest.fixture
    def correlation_data(self, request):
        """Provide correlation test data based on parameter."""
        data_sets = {
            "linear": ([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], 1.0),
            "inverse": ([1, 2, 3, 4, 5], [10, 8, 6, 4, 2], -1.0),
            "constant": ([1, 2, 3, 4, 5], [3, 3, 3, 3, 3], 0.0),
            "random": ([1, 3, 2, 5, 4], [2, 5, 3, 1, 4], 0.0),  # Near-zero correlation
            "quadratic": ([1, 2, 3, 4, 5], [1, 4, 9, 16, 25], 0.98),  # Strong but not perfect
        }
        return data_sets[request.param]

    @pytest.mark.parametrize(
        "correlation_data",
        ["linear", "inverse", "constant", "random", "quadratic"],
        indirect=True,
    )
    def test_correlation_patterns(self, analytics_manager, correlation_data):
        """Should calculate correlation for various data patterns."""
        x, y, expected = correlation_data
        result = analytics_manager.calculate_correlation(x, y)

        if expected == 0.0:
            assert abs(result) < 0.3  # Allow some tolerance for "no correlation"
        else:
            assert result == pytest.approx(expected, rel=0.05)
