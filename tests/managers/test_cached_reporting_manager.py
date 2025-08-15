"""Tests for the cached reporting manager."""

import datetime
from unittest.mock import Mock, patch

import pytest

from birdnetpi.managers.cached_reporting_manager import CachedReportingManager
from birdnetpi.services.cache_service import CacheService


@pytest.fixture
def mock_reporting_manager():
    """Mock reporting manager for testing."""
    mock = Mock()

    # Mock common methods
    mock.get_data.return_value = {"test": "data"}
    mock.get_weekly_report_data.return_value = {"week": "data"}
    mock.get_most_recent_detections.return_value = [{"detection": "1"}]
    mock.get_todays_detections.return_value = [{"today": "detection"}]
    mock.get_best_detections.return_value = [{"best": "detection"}]

    # Mock detection manager with query service
    mock.detection_manager = Mock()
    mock.detection_manager.detection_query_service = Mock()
    mock.detection_manager.detection_query_service.get_species_summary.return_value = [
        {"species": "summary"}
    ]
    mock.detection_manager.detection_query_service.get_family_summary.return_value = [
        {"family": "summary"}
    ]

    return mock


@pytest.fixture
def mock_cache_service():
    """Mock cache service for testing."""
    mock = Mock(spec=CacheService)

    # Default cache behavior - miss first time, hit second time
    mock.get.side_effect = [None, "cached_result"]
    mock.set.return_value = True
    mock.delete.return_value = True
    mock.exists.return_value = False
    mock.invalidate_pattern.return_value = True
    mock.warm_cache.return_value = {"test": True}
    mock.get_stats.return_value = {"hits": 1, "misses": 1}
    mock.health_check.return_value = {"status": "healthy"}

    return mock


class TestCachedReportingManager:
    """Test the cached reporting manager."""

    def test_init_with_caching_enabled(self, mock_reporting_manager, mock_cache_service):
        """Test initialization with caching enabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=True,
        )

        assert manager.reporting_manager == mock_reporting_manager
        assert manager.cache_service == mock_cache_service
        assert manager.enable_caching is True

    def test_init_with_caching_disabled(self, mock_reporting_manager, mock_cache_service):
        """Test initialization with caching disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        assert manager.enable_caching is False

    def test_get_cached_or_execute_cache_hit(self, mock_reporting_manager, mock_cache_service):
        """Test cache hit scenario."""
        # Reset the side_effect from fixture and set explicit return value for cache hit
        mock_cache_service.get.side_effect = None
        mock_cache_service.get.return_value = "cached_value"

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        # Mock function that shouldn't be called on cache hit
        mock_func = Mock(return_value="function_result")

        result = manager._get_cached_or_execute(
            cache_namespace="test",
            func=mock_func,
            param1="value1",
        )

        assert result == "cached_value"
        mock_cache_service.get.assert_called_once()
        mock_func.assert_not_called()  # Function shouldn't be called on cache hit
        mock_cache_service.set.assert_not_called()

    def test_get_cached_or_execute_cache_miss(self, mock_reporting_manager, mock_cache_service):
        """Test cache miss scenario."""
        mock_cache_service.get.return_value = None

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        mock_func = Mock(return_value="function_result")

        result = manager._get_cached_or_execute(
            cache_namespace="test",
            func=mock_func,
            cache_ttl=300,
            param1="value1",
        )

        assert result == "function_result"
        mock_cache_service.get.assert_called_once()
        mock_func.assert_called_once_with(param1="value1")
        mock_cache_service.set.assert_called_once_with(
            "test", "function_result", ttl=300, param1="value1"
        )

    def test_get_cached_or_execute_caching_disabled(
        self, mock_reporting_manager, mock_cache_service
    ):
        """Test behavior when caching is disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        mock_func = Mock(return_value="function_result")

        result = manager._get_cached_or_execute(
            cache_namespace="test",
            func=mock_func,
            param1="value1",
        )

        assert result == "function_result"
        mock_func.assert_called_once_with(param1="value1")
        # Cache should not be accessed when disabled
        mock_cache_service.get.assert_not_called()
        mock_cache_service.set.assert_not_called()

    def test_get_cached_or_execute_error_fallback(self, mock_reporting_manager, mock_cache_service):
        """Test fallback to direct execution when cache errors occur."""
        mock_cache_service.get.side_effect = Exception("Cache error")

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        mock_func = Mock(return_value="function_result")

        result = manager._get_cached_or_execute(
            cache_namespace="test",
            func=mock_func,
            param1="value1",
        )

        assert result == "function_result"
        mock_func.assert_called_once_with(param1="value1")

    def test_get_data_caching(self, mock_reporting_manager, mock_cache_service):
        """Test get_data with caching."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_data(use_l10n_data=True, language_code="en")

        assert result == {"test": "data"}
        mock_reporting_manager.get_data.assert_called_once_with(
            use_l10n_data=True, language_code="en"
        )

    def test_get_weekly_report_data_caching(self, mock_reporting_manager, mock_cache_service):
        """Test get_weekly_report_data with caching."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_weekly_report_data()

        assert result == {"week": "data"}
        mock_reporting_manager.get_weekly_report_data.assert_called_once()

    def test_get_most_recent_detections_caching(self, mock_reporting_manager, mock_cache_service):
        """Test get_most_recent_detections with caching."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_most_recent_detections(limit=5, language_code="es")

        assert result == [{"detection": "1"}]
        mock_reporting_manager.get_most_recent_detections.assert_called_once_with(
            limit=5, language_code="es", use_l10n_data=True
        )

    def test_get_todays_detections_with_date_key(self, mock_reporting_manager, mock_cache_service):
        """Test get_todays_detections includes date in cache key."""
        with patch("birdnetpi.managers.cached_reporting_manager.datetime") as mock_datetime:
            # Create a mock date object that returns "2025-01-15" when isoformat() is called
            mock_date = Mock()
            mock_date.isoformat.return_value = "2025-01-15"
            mock_datetime.date.today.return_value = mock_date

            manager = CachedReportingManager(
                reporting_manager=mock_reporting_manager,
                cache_service=mock_cache_service,
            )

            result = manager.get_todays_detections(language_code="fr")

            assert result == [{"today": "detection"}]
            # Function should be called without date parameter
            mock_reporting_manager.get_todays_detections.assert_called_once_with(
                language_code="fr", use_l10n_data=True
            )

            # Cache should be called with date parameter for key generation
            mock_cache_service.get.assert_called_with(
                "todays_detections", date="2025-01-15", language_code="fr", use_l10n_data=True
            )

    def test_get_best_detections_caching(self, mock_reporting_manager, mock_cache_service):
        """Test get_best_detections with caching."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_best_detections(limit=15)

        assert result == [{"best": "detection"}]
        mock_reporting_manager.get_best_detections.assert_called_once_with(limit=15)

    def test_get_species_summary_with_detection_query_service(
        self, mock_reporting_manager, mock_cache_service
    ):
        """Test get_species_summary using detection query service."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        since_date = datetime.datetime(2025, 1, 1)
        result = manager.get_species_summary(
            language_code="en", since=since_date, family_filter="Turdidae"
        )

        assert result == [{"species": "summary"}]
        mock_reporting_manager.detection_manager.detection_query_service.get_species_summary.assert_called_once_with(
            language_code="en", since=since_date, family_filter="Turdidae"
        )

    def test_get_species_summary_without_detection_query_service(
        self, mock_reporting_manager, mock_cache_service
    ):
        """Test get_species_summary fallback when detection query service unavailable."""
        # Remove detection query service
        mock_reporting_manager.detection_manager.detection_query_service = None

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_species_summary(language_code="en")

        assert result == []

    def test_get_family_summary_with_detection_query_service(
        self, mock_reporting_manager, mock_cache_service
    ):
        """Test get_family_summary using detection query service."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        since_date = datetime.datetime(2025, 1, 1)
        result = manager.get_family_summary(language_code="de", since=since_date)

        assert result == [{"family": "summary"}]
        mock_reporting_manager.detection_manager.detection_query_service.get_family_summary.assert_called_once_with(
            language_code="de", since=since_date
        )

    def test_invalidate_detection_caches(self, mock_reporting_manager, mock_cache_service):
        """Test detection cache invalidation."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.invalidate_detection_caches()

        assert result is True
        # Check that all expected cache namespaces are invalidated
        expected_calls = [
            "recent_detections",
            "todays_detections",
            "best_detections",
            "species_summary",
            "family_summary",
            "all_detection_data",
        ]

        assert mock_cache_service.invalidate_pattern.call_count == len(expected_calls)

    def test_invalidate_detection_caches_disabled(self, mock_reporting_manager, mock_cache_service):
        """Test detection cache invalidation when caching is disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        result = manager.invalidate_detection_caches()

        assert result is True
        mock_cache_service.invalidate_pattern.assert_not_called()

    def test_invalidate_report_caches(self, mock_reporting_manager, mock_cache_service):
        """Test report cache invalidation."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.invalidate_report_caches()

        assert result is True
        mock_cache_service.invalidate_pattern.assert_called_once_with("weekly_report")

    def test_warm_common_caches(self, mock_reporting_manager, mock_cache_service):
        """Test cache warming for common queries."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.warm_common_caches()

        assert result == {"test": True}
        mock_cache_service.warm_cache.assert_called_once()

        # Verify warming functions were passed
        call_args = mock_cache_service.warm_cache.call_args[0][0]
        assert len(call_args) >= 4  # At least 4 basic warming functions

    def test_warm_common_caches_disabled(self, mock_reporting_manager, mock_cache_service):
        """Test cache warming when caching is disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        result = manager.warm_common_caches()

        assert result == {}
        mock_cache_service.warm_cache.assert_not_called()

    def test_get_cache_stats(self, mock_reporting_manager, mock_cache_service):
        """Test getting cache statistics."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_cache_stats()

        expected = {"hits": 1, "misses": 1, "caching_enabled": True}
        assert result == expected
        mock_cache_service.get_stats.assert_called_once()

    def test_get_cache_stats_disabled(self, mock_reporting_manager, mock_cache_service):
        """Test getting cache statistics when caching is disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        result = manager.get_cache_stats()

        assert result == {"caching_enabled": False}
        mock_cache_service.get_stats.assert_not_called()

    def test_get_cache_health(self, mock_reporting_manager, mock_cache_service):
        """Test getting cache health status."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        result = manager.get_cache_health()

        expected = {"status": "healthy", "caching_enabled": True}
        assert result == expected
        mock_cache_service.health_check.assert_called_once()

    def test_get_cache_health_disabled(self, mock_reporting_manager, mock_cache_service):
        """Test getting cache health when caching is disabled."""
        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
            enable_caching=False,
        )

        result = manager.get_cache_health()

        assert result == {"caching_enabled": False, "status": "disabled"}
        mock_cache_service.health_check.assert_not_called()

    def test_proxy_methods(self, mock_reporting_manager, mock_cache_service):
        """Test proxy methods for non-cached functionality."""
        mock_reporting_manager.date_filter.return_value = "filtered_df"
        mock_reporting_manager.get_daily_detection_data_for_plotting.return_value = "plot_data"

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        # Test date_filter proxy
        result1 = manager.date_filter("df", "2025-01-01", "2025-01-31")
        assert result1 == "filtered_df"
        mock_reporting_manager.date_filter.assert_called_once_with("df", "2025-01-01", "2025-01-31")

        # Test plotting data proxy
        result2 = manager.get_daily_detection_data_for_plotting("df", "1h", "Robin")
        assert result2 == "plot_data"
        mock_reporting_manager.get_daily_detection_data_for_plotting.assert_called_once_with(
            "df", "1h", "Robin"
        )

    def test_cache_error_handling(self, mock_reporting_manager, mock_cache_service):
        """Test error handling during cache operations."""
        # Setup cache service to raise errors
        mock_cache_service.invalidate_pattern.side_effect = Exception("Cache error")

        manager = CachedReportingManager(
            reporting_manager=mock_reporting_manager,
            cache_service=mock_cache_service,
        )

        # Should handle cache errors gracefully
        result = manager.invalidate_detection_caches()
        assert result is False  # Should return False on error

        result = manager.invalidate_report_caches()
        assert result is False  # Should return False on error
