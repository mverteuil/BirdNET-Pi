"""Cached reporting manager that wraps the reporting manager with caching capabilities.

This manager extends the existing reporting functionality by adding intelligent caching
for expensive analytics queries. It uses the cache service to minimize database queries
and improve dashboard performance, particularly important for SBC deployments.

Key features:
- Transparent caching layer over existing reporting functionality
- Cache warming for common queries on startup
- Automatic cache invalidation strategies
- Cache-aware error handling and graceful degradation
"""

import datetime
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from birdnetpi.managers.reporting_manager import ReportingManager
    from birdnetpi.services.cache_service import CacheService

logger = structlog.get_logger(__name__)


class CachedReportingManager:
    """Cached wrapper for ReportingManager with intelligent caching strategies.

    This manager provides a caching layer over the existing ReportingManager to improve
    performance of expensive analytics queries. It implements cache warming, invalidation,
    and graceful fallback to ensure reliability.
    """

    def __init__(
        self,
        reporting_manager: "ReportingManager",
        cache_service: "CacheService",
        enable_caching: bool = True,
    ):
        """Initialize cached reporting manager.

        Args:
            reporting_manager: The underlying reporting manager
            cache_service: Cache service for storing query results
            enable_caching: Whether to enable caching (for testing/debugging)
        """
        self.reporting_manager = reporting_manager
        self.cache_service = cache_service
        self.enable_caching = enable_caching

        if not enable_caching:
            logger.info("Caching disabled for reporting manager")

    def _get_cached_or_execute(
        self,
        cache_namespace: str,
        func: Callable[..., Any],
        cache_ttl: int | None = None,
        cache_key_params: dict[str, Any] | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Get data from cache or execute function and cache result.

        Args:
            cache_namespace: Cache namespace for the query
            func: Function to execute if cache miss
            cache_ttl: Custom TTL for this query
            cache_key_params: Additional parameters for cache key generation only
            **kwargs: Parameters for function execution and cache key generation

        Returns:
            Cached or freshly computed result
        """
        if not self.enable_caching:
            return func(**kwargs)

        try:
            # Combine function params and cache-only params for cache key generation
            cache_params = kwargs.copy()
            if cache_key_params:
                cache_params.update(cache_key_params)

            # Try to get from cache first
            cached_result = self.cache_service.get(cache_namespace, **cache_params)
            if cached_result is not None:
                logger.debug("Cache hit for analytics query", namespace=cache_namespace)
                return cached_result

            # Cache miss - execute function (only with function params)
            logger.debug("Cache miss, executing query", namespace=cache_namespace)
            result = func(**kwargs)

            # Cache the result (using cache params for key generation)
            self.cache_service.set(cache_namespace, result, ttl=cache_ttl, **cache_params)
            return result

        except Exception as e:
            logger.error(
                "Cache error, falling back to direct execution",
                namespace=cache_namespace,
                error=str(e),
            )
            # Fallback to direct execution on cache errors
            return func(**kwargs)

    def get_data(self, use_l10n_data: bool = True, language_code: str = "en") -> Any:  # noqa: ANN401
        """Get all detection data with caching.

        Args:
            use_l10n_data: Whether to use translation data
            language_code: Language for translations

        Returns:
            Cached or fresh DataFrame with detection data
        """
        return self._get_cached_or_execute(
            cache_namespace="all_detection_data",
            func=self.reporting_manager.get_data,
            cache_ttl=600,  # 10 minutes for comprehensive data
            use_l10n_data=use_l10n_data,
            language_code=language_code,
        )

    def get_weekly_report_data(self) -> dict[str, Any]:
        """Get weekly report data with caching.

        Returns:
            Cached or fresh weekly report data
        """
        # Cache weekly reports for longer since they're based on fixed time periods
        return self._get_cached_or_execute(
            cache_namespace="weekly_report",
            func=self.reporting_manager.get_weekly_report_data,
            cache_ttl=3600,  # 1 hour - weekly data changes less frequently
        )

    def get_most_recent_detections(
        self,
        limit: int = 10,
        language_code: str = "en",
        use_l10n_data: bool = True,
    ) -> list[dict[str, Any]]:
        """Get most recent detections with caching.

        Args:
            limit: Maximum number of detections to return
            language_code: Language for translations
            use_l10n_data: Whether to include translation data

        Returns:
            Cached or fresh list of recent detections
        """
        return self._get_cached_or_execute(
            cache_namespace="recent_detections",
            func=self.reporting_manager.get_most_recent_detections,
            cache_ttl=60,  # 1 minute - recent detections change frequently
            limit=limit,
            language_code=language_code,
            use_l10n_data=use_l10n_data,
        )

    def get_todays_detections(
        self,
        language_code: str = "en",
        use_l10n_data: bool = True,
    ) -> list[dict[str, Any]]:
        """Get today's detections with caching.

        Args:
            language_code: Language for translations
            use_l10n_data: Whether to include translation data

        Returns:
            Cached or fresh list of today's detections
        """
        # Use current date in cache key to ensure daily invalidation
        today_str = datetime.date.today().isoformat()

        return self._get_cached_or_execute(
            cache_namespace="todays_detections",
            func=self.reporting_manager.get_todays_detections,
            cache_ttl=300,  # 5 minutes - today's data changes regularly
            cache_key_params={"date": today_str},
            language_code=language_code,
            use_l10n_data=use_l10n_data,
        )

    def get_best_detections(self, limit: int = 20) -> list[dict]:
        """Get best detections with caching.

        Args:
            limit: Maximum number of best detections to return

        Returns:
            Cached or fresh list of best detections
        """
        return self._get_cached_or_execute(
            cache_namespace="best_detections",
            func=self.reporting_manager.get_best_detections,
            cache_ttl=1800,  # 30 minutes - best detections change slowly
            limit=limit,
        )

    def get_species_summary(
        self,
        language_code: str = "en",
        since: datetime.datetime | None = None,
        family_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get species summary with caching.

        This method uses the detection query service if available for enhanced data.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp
            family_filter: Filter by taxonomic family

        Returns:
            Cached or fresh species summary data
        """
        if (
            hasattr(self.reporting_manager, "detection_manager")
            and hasattr(self.reporting_manager.detection_manager, "detection_query_service")
            and self.reporting_manager.detection_manager.detection_query_service
        ):
            # Use detection query service for enhanced data
            detection_query_service = (
                self.reporting_manager.detection_manager.detection_query_service
            )

            return self._get_cached_or_execute(
                cache_namespace="species_summary",
                func=detection_query_service.get_species_summary,
                cache_ttl=900,  # 15 minutes
                language_code=language_code,
                since=since,
                family_filter=family_filter,
            )
        else:
            # Fallback to basic implementation
            logger.warning("Detection query service not available, species summary limited")
            return []

    def get_family_summary(
        self,
        language_code: str = "en",
        since: datetime.datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get family summary with caching.

        Args:
            language_code: Language for translations
            since: Only include detections after this timestamp

        Returns:
            Cached or fresh family summary data
        """
        if (
            hasattr(self.reporting_manager, "detection_manager")
            and hasattr(self.reporting_manager.detection_manager, "detection_query_service")
            and self.reporting_manager.detection_manager.detection_query_service
        ):
            # Use detection query service for enhanced data
            detection_query_service = (
                self.reporting_manager.detection_manager.detection_query_service
            )

            return self._get_cached_or_execute(
                cache_namespace="family_summary",
                func=detection_query_service.get_family_summary,
                cache_ttl=1200,  # 20 minutes
                language_code=language_code,
                since=since,
            )
        else:
            # Fallback to basic implementation
            logger.warning("Detection query service not available, family summary limited")
            return []

    def invalidate_detection_caches(self) -> bool:
        """Invalidate all detection-related caches.

        Call this when new detections are added or detection data changes.

        Returns:
            True if successful, False otherwise
        """
        if not self.enable_caching:
            return True

        try:
            logger.info("Invalidating detection-related caches")

            # Invalidate specific cache namespaces
            cache_namespaces = [
                "recent_detections",
                "todays_detections",
                "best_detections",
                "species_summary",
                "family_summary",
            ]

            success_count = 0
            for namespace in cache_namespaces:
                if self.cache_service.invalidate_pattern(namespace):
                    success_count += 1

            # Also invalidate comprehensive data cache
            self.cache_service.invalidate_pattern("all_detection_data")

            logger.info(
                "Cache invalidation completed",
                namespaces_invalidated=success_count,
                total_namespaces=len(cache_namespaces),
            )

            return success_count == len(cache_namespaces)

        except Exception as e:
            logger.error("Cache invalidation failed", error=str(e))
            return False

    def invalidate_report_caches(self) -> bool:
        """Invalidate report-specific caches.

        Call this when report parameters or time-based data changes.

        Returns:
            True if successful, False otherwise
        """
        if not self.enable_caching:
            return True

        try:
            logger.info("Invalidating report caches")
            return self.cache_service.invalidate_pattern("weekly_report")
        except Exception as e:
            logger.error("Report cache invalidation failed", error=str(e))
            return False

    def warm_common_caches(self) -> dict[str, bool]:
        """Warm cache with common queries for better performance.

        This should be called during application startup or periodically
        to ensure frequently accessed data is cached.

        Returns:
            Dictionary mapping cache namespace to warming success status
        """
        if not self.enable_caching:
            logger.info("Cache warming skipped - caching disabled")
            return {}

        logger.info("Starting cache warming for common analytics queries")

        # Define common warming queries
        warming_functions = [
            # Recent detections in multiple languages
            (
                "recent_detections",
                self.reporting_manager.get_most_recent_detections,
                {"limit": 10, "language_code": "en", "use_l10n_data": True},
                60,
            ),
            # Today's detections
            (
                "todays_detections",
                self.reporting_manager.get_todays_detections,
                {"language_code": "en", "use_l10n_data": True},
                300,
            ),
            # Weekly report data
            ("weekly_report", self.reporting_manager.get_weekly_report_data, {}, 3600),
            # Best detections
            ("best_detections", self.reporting_manager.get_best_detections, {"limit": 20}, 1800),
        ]

        # Add species and family summaries if detection query service is available
        if (
            hasattr(self.reporting_manager, "detection_manager")
            and hasattr(self.reporting_manager.detection_manager, "detection_query_service")
            and self.reporting_manager.detection_manager.detection_query_service
        ):
            detection_query_service = (
                self.reporting_manager.detection_manager.detection_query_service
            )

            warming_functions.extend(
                [
                    (
                        "species_summary",
                        detection_query_service.get_species_summary,
                        {"language_code": "en"},
                        900,
                    ),
                    (
                        "family_summary",
                        detection_query_service.get_family_summary,
                        {"language_code": "en"},
                        1200,
                    ),
                ]
            )

        return self.cache_service.warm_cache(warming_functions)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache performance statistics.

        Returns:
            Dictionary containing cache performance metrics
        """
        if not self.enable_caching:
            return {"caching_enabled": False}

        stats = self.cache_service.get_stats()
        stats["caching_enabled"] = True
        return stats

    def get_cache_health(self) -> dict[str, Any]:
        """Get cache health status.

        Returns:
            Dictionary containing cache health information
        """
        if not self.enable_caching:
            return {"caching_enabled": False, "status": "disabled"}

        health = self.cache_service.health_check()
        health["caching_enabled"] = True
        return health

    # Proxy methods for non-cached functionality
    def date_filter(self, df: Any, start_date: str, end_date: str) -> Any:  # noqa: ANN401
        """Proxy to original date_filter method."""
        return self.reporting_manager.date_filter(df, start_date, end_date)

    def get_daily_detection_data_for_plotting(
        self,
        df: Any,  # noqa: ANN401
        resample_selection: str,
        species: str,
    ) -> Any:  # noqa: ANN401
        """Proxy to original plotting data preparation method."""
        return self.reporting_manager.get_daily_detection_data_for_plotting(
            df, resample_selection, species
        )
