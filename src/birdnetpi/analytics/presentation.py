import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Generic, TypeVar

from pydantic import BaseModel

from birdnetpi.analytics.analytics import (
    AnalyticsManager,
    DashboardSummaryDict,
    ScatterDataDict,
    SpeciesFrequencyDict,
    TemporalPatternsDict,
)
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import DetectionBase
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.signals import detection_signal
from birdnetpi.utils.cache.cache import Cache

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MetricsDict(BaseModel):
    """Formatted metrics for display."""

    species_detected: str
    detections_today: str
    species_week: str
    storage: str
    hours: str
    threshold: str


class DetectionLogEntry(BaseModel):
    """Detection log entry for display."""

    time: str
    species: str
    confidence: str


class SpeciesListEntry(BaseModel):
    """Species frequency list entry."""

    name: str
    count: int
    bar_width: str


class ScatterDataPoint(BaseModel):
    """Scatter plot data point."""

    x: float
    y: float
    species: str
    color: str


class LandingPageData(BaseModel):
    """Complete landing page data (without system status - fetched client-side)."""

    metrics: MetricsDict
    detection_log: list[DetectionLogEntry]
    species_frequency: list[SpeciesListEntry]
    hourly_distribution: list[int]
    visualization_data: list[ScatterDataPoint]


class APIResponse(BaseModel, Generic[T]):
    """Generic API response format."""

    status: str
    timestamp: str
    data: T


class DashboardSummary(BaseModel):
    """Dashboard summary data from analytics."""

    species_total: int
    detections_today: int
    species_week: int
    storage_gb: float
    hours_monitored: float
    confidence_threshold: float


class SpeciesFrequencyItem(BaseModel):
    """Species frequency analysis item."""

    name: str
    count: int
    percentage: float
    category: str


class TemporalPatterns(BaseModel):
    """Temporal detection patterns."""

    hourly_distribution: list[int]
    peak_hour: int | None
    periods: dict[str, int]


class PresentationManager:
    """Formats data for presentation in UI/API responses."""

    def __init__(
        self,
        analytics_manager: AnalyticsManager,
        detection_query_service: DetectionQueryService,
        config: BirdNETConfig,
        cache: Cache | None = None,
    ):
        self.analytics_manager = analytics_manager
        self.detection_query_service = detection_query_service
        self.config = config
        self.cache = cache

        # Subscribe to detection signal for cache invalidation
        if self.cache:
            detection_signal.connect(self._invalidate_detection_cache)

    # --- Landing Page ---

    async def get_landing_page_data_safe(self) -> LandingPageData:
        """Get landing page data with error handling and fallback values."""
        try:
            return await self.get_landing_page_data()
        except Exception:
            logger.exception("Failed to get landing page data")
            # Return safe defaults
            return LandingPageData(
                metrics=MetricsDict(
                    species_detected="0",
                    detections_today="0",
                    species_week="0",
                    storage="0 GB",
                    hours="0",
                    threshold="≥0.70",
                ),
                detection_log=[],
                species_frequency=[],
                hourly_distribution=[0] * 24,
                visualization_data=[],
            )

    async def get_landing_page_data(self) -> LandingPageData:
        """Format all data needed for landing page."""
        summary = await self.analytics_manager.get_dashboard_summary()
        frequency = await self.analytics_manager.get_species_frequency_analysis()
        temporal = await self.analytics_manager.get_temporal_patterns()
        recent = await self.detection_query_service.query_detections(
            limit=10, order_by="timestamp", order_desc=True
        )
        scatter = await self.analytics_manager.get_detection_scatter_data()

        return LandingPageData(
            metrics=self._format_metrics(summary),
            detection_log=self._format_detection_log(recent),
            # Send top 20 species for client-side buffering
            species_frequency=self._format_species_list(frequency[:20]),
            hourly_distribution=temporal["hourly_distribution"],
            visualization_data=self._format_scatter_data(scatter),
        )

    def _format_metrics(self, summary: DashboardSummaryDict) -> MetricsDict:
        """Format summary metrics for display."""
        return MetricsDict(
            species_detected=f"{summary['species_total']:,}",
            detections_today=f"{summary['detections_today']:,}",
            species_week=f"{summary['species_week']:,}",
            storage=f"{summary['storage_gb']:.1f} GB",
            hours=f"{summary['hours_monitored']:.0f}",
            threshold=f"≥{summary['confidence_threshold']:.2f}",
        )

    def _format_detection_log(self, detections: Sequence[DetectionBase]) -> list[DetectionLogEntry]:
        """Format recent detections for display."""
        return [
            DetectionLogEntry(
                time=d.timestamp.strftime("%H:%M"),
                species=d.common_name or d.scientific_name,
                confidence=f"{d.confidence:.0%}",
            )
            for d in detections
        ]

    def _format_species_list(
        self, frequency_data: list[SpeciesFrequencyDict]
    ) -> list[SpeciesListEntry]:
        """Format species frequency for display."""
        max_count = frequency_data[0]["count"] if frequency_data else 1

        return [
            SpeciesListEntry(
                name=f["name"],
                count=f["count"],
                bar_width=f"{(f['count'] / max_count) * 100:.0f}%",
            )
            for f in frequency_data
        ]

    def _format_scatter_data(self, scatter_data: list[ScatterDataDict]) -> list[ScatterDataPoint]:
        """Format scatter plot data for visualization."""
        return [
            ScatterDataPoint(
                x=d["time"],
                y=d["confidence"],
                species=d["species"],
                color={"common": "#2e7d32", "regular": "#f57c00", "uncommon": "#c62828"}.get(
                    d["frequency_category"], "#666"
                ),
            )
            for d in scatter_data
        ]

    # --- Detection Display Page ---

    def _calculate_period_range(self, period: str) -> tuple[datetime | None, str]:
        """Calculate start date and label for the given period.

        Args:
            period: Time period to display

        Returns:
            Tuple of (start_date, period_label)
        """
        from datetime import timedelta

        import pytz

        # Get the configured timezone
        user_tz = pytz.timezone(self.config.timezone) if self.config.timezone != "UTC" else UTC

        # Get current time in user's timezone
        now_utc = datetime.now(UTC)
        now_local = now_utc.astimezone(user_tz)

        # Calculate "today" start in user's timezone, then convert back to UTC for queries
        today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today = today_local.astimezone(UTC)  # Convert back to UTC for database queries

        period_configs = {
            "day": (today, "Today"),
            "week": (today - timedelta(days=7), "This Week"),
            "month": (today - timedelta(days=30), "This Month"),
            "season": (today - timedelta(days=90), "This Season"),
            "year": (today - timedelta(days=365), "This Year"),
            "historical": (None, "All Time"),
        }

        return period_configs.get(period, period_configs["day"])

    def _get_period_label(self, period: str) -> str:
        """Get human-readable label for the period.

        Args:
            period: Period identifier

        Returns:
            Human-readable period label
        """
        period_labels = {
            "day": "Today",
            "week": "This Week",
            "month": "This Month",
            "season": "This Season",
            "year": "This Year",
            "historical": "All Time",
        }
        return period_labels.get(period, "This Period")

    async def _get_species_summary_data(
        self, detection_query_service: "DetectionQueryService | None", start_date: datetime | None
    ) -> list:
        """Get species summary data from appropriate source.

        Args:
            detection_query_service: Optional detection query service
            start_date: Start date for filtering

        Returns:
            List of species summary data
        """
        if detection_query_service:
            return await detection_query_service.get_species_summary(
                language_code=self.config.language,
                since=start_date,
            )
        else:
            # Use get_species_counts which returns list of dicts
            end_time = datetime.now(UTC)
            # For historical data, use a very old date with timezone
            default_start = datetime(1970, 1, 1, tzinfo=UTC) if start_date is None else start_date
            return await self.detection_query_service.get_species_counts(
                start_time=default_start, end_time=end_time
            )

    def _format_species_frequency(self, species_summary: list, period: str) -> list:
        """Format species frequency table data.

        Args:
            species_summary: List of species data
            period: Current period for display

        Returns:
            Formatted species frequency list
        """
        species_frequency = []
        if not isinstance(species_summary, list):
            return species_frequency

        for species in species_summary[:10]:  # Top 10 species
            # Extract name and scientific name from dict or object
            if isinstance(species, dict):
                name = (
                    species.get("translated_name", None)
                    or species.get("best_common_name", None)
                    or species.get("common_name", None)
                    or species.get("scientific_name", "Unknown")
                )
                scientific_name = species.get("scientific_name", "Unknown")
                count = species.get("detection_count", species.get("count", 0))
            else:
                name = (
                    getattr(species, "translated_name", None)
                    or getattr(species, "best_common_name", None)
                    or getattr(species, "common_name", None)
                    or getattr(species, "scientific_name", "Unknown")
                )
                scientific_name = getattr(species, "scientific_name", "Unknown")
                count = getattr(species, "count", 0)

            species_frequency.append(
                {
                    "name": name,
                    "scientific_name": scientific_name,  # Add scientific name for filtering
                    "count": count,  # Keep raw count for statistics
                    "today": count if period == "day" else "-",
                    "week": count if period == "week" else "-",
                    "month": count,
                    "trend": "-",  # No trend - doesn't make sense without comparison data
                }
            )

        return species_frequency

    def _format_top_species(self, species_summary: list) -> list:
        """Format top species for sparkline display.

        Args:
            species_summary: List of species data

        Returns:
            Formatted top species list
        """
        top_species = []
        if not isinstance(species_summary, list):
            return top_species

        for i, species in enumerate(species_summary[:6]):  # Top 6 species
            if isinstance(species, dict):
                common_name = (
                    species.get("translated_name")
                    or species.get("best_common_name")
                    or species.get("common_name", "Unknown")
                )
                scientific_name = species.get("scientific_name", "")
                count = species.get("detection_count", 0) or species.get("count", 0)
            else:
                common_name = getattr(species, "common_name", "Unknown")
                scientific_name = getattr(species, "scientific_name", "")
                count = getattr(species, "count", 0)

            top_species.append(
                {
                    "id": f"species-{i}",
                    "common_name": common_name,
                    "scientific_name": scientific_name,
                    "count": count,
                }
            )

        return top_species

    async def _generate_sparkline_data(self, top_species: list, period: str) -> dict:
        """Generate sparkline data for top species.

        Args:
            top_species: List of top species
            period: Current period for display

        Returns:
            Dictionary of sparkline data
        """
        sparkline_data = {}

        # Determine number of days based on period
        period_days = {
            "day": 1,
            "week": 7,
            "month": 30,
            "season": 90,
            "year": 365,
            "historical": 3650,  # ~10 years
        }
        days_to_analyze = period_days.get(period, 1)

        for species in top_species:
            # Get species-specific hourly pattern using scientific name
            scientific_name = species.get("scientific_name")
            common_name = species.get("common_name")

            # Try scientific name first, then common name
            species_pattern = None
            if scientific_name:
                species_pattern = await self.analytics_manager.get_species_hourly_patterns(
                    scientific_name, days=days_to_analyze
                )
            if not species_pattern or all(v == 0 for v in species_pattern):
                if common_name:
                    species_pattern = await self.analytics_manager.get_species_hourly_patterns(
                        common_name, days=days_to_analyze
                    )

            sparkline_data[f"{species['id']}-spark"] = (
                species_pattern if species_pattern else [0] * 24
            )

        return sparkline_data

    async def _get_period_temporal_patterns(
        self, period: str, now: datetime
    ) -> TemporalPatternsDict:
        """Get temporal patterns for the specified period.

        Args:
            period: Time period ('day', 'week', etc.)
            now: Current datetime

        Returns:
            Dictionary with hourly_distribution, peak_hour, and periods
        """
        if period == "day":
            return await self.analytics_manager.get_temporal_patterns(date=now.date())

        # Map period to days for calculation
        period_days = {
            "week": 7,
            "month": 30,
            "season": 90,
            "year": 365,
            "historical": 3650,  # 10 years
        }
        days = period_days.get(period, 7)

        # Get aggregated hourly pattern for the actual period
        weekday_hourly = await self.analytics_manager.get_aggregate_hourly_pattern(days=days)

        # Combine all weekdays to get overall hourly distribution
        hourly_dist = [0] * 24
        for day_data in weekday_hourly:
            for hour, count in enumerate(day_data):
                if hour < 24:
                    hourly_dist[hour] += count

        # Find the actual peak hour
        max_count = max(hourly_dist) if hourly_dist else 0
        peak_hour = hourly_dist.index(max_count) if max_count > 0 else 6

        return {
            "hourly_distribution": hourly_dist,
            "peak_hour": peak_hour,
            "periods": {},  # Not used for non-day views
        }

    def _invalidate_detection_cache(self, sender: object, **kwargs: object) -> None:
        """Invalidate detection-related cache when new detection arrives.

        This is called by the detection signal when a new detection is created.
        """
        if not self.cache:
            return

        logger.debug("Invalidating detection cache due to new detection")
        # Invalidate all detection display caches for different periods
        for period in ["day", "week", "month", "season", "year", "historical"]:
            self.cache.delete("detection_display_data", period=period)
        logger.debug("Detection cache invalidated")

    async def get_detection_display_data(
        self, period: str, detection_query_service: "DetectionQueryService"
    ) -> dict:
        """Format all data needed for detection display page.

        Args:
            period: Time period to display ('day', 'week', 'month', 'season', 'year', 'historical')
            detection_query_service: Optional DetectionQueryService for localized data

        Returns:
            Dictionary with all formatted data for the template
        """
        # Check cache first if available
        if self.cache:
            cached_data = self.cache.get("detection_display_data", period=period)
            if cached_data is not None:
                logger.debug(f"Returning cached detection display data for period: {period}")
                return cached_data
        # Calculate time ranges based on period
        start_date, _period_label = self._calculate_period_range(period)

        # For display, use the current time in UTC
        now = datetime.now(UTC)

        # Get detections with localization if service is available
        # We'll load detections via AJAX, so just provide empty list initially
        recent_detections = []

        # Parallelize independent async operations for better performance
        # These operations don't depend on each other and can run concurrently
        (
            species_summary,
            temporal_patterns,
            dashboard_summary,
            weekly_data,
        ) = await asyncio.gather(
            self._get_species_summary_data(detection_query_service, start_date),
            self._get_period_temporal_patterns(period, now),
            self.analytics_manager.get_dashboard_summary(),
            self.analytics_manager.get_weekly_patterns(),
        )

        # Format species frequency table (synchronous, depends on species_summary)
        species_frequency = self._format_species_frequency(species_summary, period)

        # Removed: top_species and sparkline generation (charts removed per requirements)

        # Format for display with total counts per day
        weekly_patterns = [
            {"id": "sun", "name": "Sunday", "count": sum(weekly_data.get("sun", []))},
            {"id": "mon", "name": "Monday", "count": sum(weekly_data.get("mon", []))},
            {"id": "tue", "name": "Tuesday", "count": sum(weekly_data.get("tue", []))},
            {"id": "wed", "name": "Wednesday", "count": sum(weekly_data.get("wed", []))},
            {"id": "thu", "name": "Thursday", "count": sum(weekly_data.get("thu", []))},
            {"id": "fri", "name": "Friday", "count": sum(weekly_data.get("fri", []))},
            {"id": "sat", "name": "Saturday", "count": sum(weekly_data.get("sat", []))},
        ]

        # Removed: week_patterns_data generation (charts removed per requirements)

        # Calculate statistics based on the actual species summary data
        # Use the full species_summary for accurate counts, not the formatted frequency
        period_species = len(species_summary) if species_summary else 0
        period_detections = (
            sum(s.get("detection_count", s.get("count", 0)) for s in species_summary)
            if species_summary
            else 0
        )

        # Find peak activity time from temporal patterns
        peak_hour = temporal_patterns.get("peak_hour", 6)
        if peak_hour is None:
            peak_hour = 6
        hourly_dist = temporal_patterns.get("hourly_distribution", [0] * 24)
        peak_detections = hourly_dist[peak_hour] if 0 <= peak_hour < len(hourly_dist) else 0
        peak_activity_time = f"{peak_hour:02d}:00-{(peak_hour + 1):02d}:00"

        # Get new species for the period (take rare/uncommon species)
        new_species = []
        new_species_period = "week" if period == "day" else "period"
        if species_summary and len(species_summary) > 0:
            # Take species with low detection counts as potentially "new"
            # Sort by count to get the rarest first
            sorted_species = sorted(
                species_summary, key=lambda x: x.get("detection_count", x.get("count", 0))
            )
            for species in sorted_species[:5]:  # Check first 5 rarest
                if isinstance(species, dict):
                    # Get common name using same logic as species frequency
                    common_name = (
                        species.get("translated_name", None)
                        or species.get("best_common_name", None)
                        or species.get("common_name", None)
                        or species.get("scientific_name", "Unknown")
                    )
                    count = species.get("detection_count", species.get("count", 0))
                    # Consider species with very few detections as "new"
                    if common_name and count <= 3:
                        new_species.append(common_name)
                        if len(new_species) >= 2:  # Limit to 2 for display
                            break

        trend_percentage = 18  # Would calculate from historical data

        result = {
            # Page metadata
            "location": self.config.site_name,
            "current_date": now.strftime("%B %d, %Y"),
            "species_count": dashboard_summary["species_total"],
            # Statistics line (context-aware for period)
            "today_species": period_species,
            "today_detections": period_detections,
            "peak_activity_time": peak_activity_time,
            "peak_detections": peak_detections,
            "new_species": new_species[:2],  # Limit to 2 for display
            "new_species_period": new_species_period,  # Context for the period
            "trend_symbol": "↑" if trend_percentage > 0 else "↓" if trend_percentage < 0 else "→",
            "trend_percentage": abs(trend_percentage),
            # Main data
            "recent_detections": recent_detections,
            "species_frequency": species_frequency,
            "weekly_patterns": weekly_patterns,
            # Configuration
            "period": period,  # Pass current period for template highlighting
            "period_label": self._get_period_label(period),  # Human-readable period label
            "confidence_threshold": self.config.species_confidence_threshold,
            "migration_note": "Migration period may affect species diversity through October."
            if 8 <= now.month <= 10
            else None,
        }

        # Cache the result if cache is available
        if self.cache:
            # Cache for 5 minutes or until new detection arrives
            self.cache.set("detection_display_data", result, ttl=300, period=period)

        return result

    # --- API Responses ---

    def format_api_response(self, data: T, status: str = "success") -> APIResponse[T]:
        """Format data for API response."""
        return APIResponse(status=status, timestamp=datetime.now().isoformat(), data=data)

    # === NEW ANALYSIS PAGE METHODS ===

    async def get_analysis_page_data(
        self,
        primary_period: str,
        comparison_period: str | None = None,
        analysis_types: list[str] | None = None,
        progressive: bool = True,
    ) -> dict:
        """Format comprehensive analysis page data.

        Args:
            primary_period: Main period to analyze ("day", "week", "month", "season", "year")
            comparison_period: Optional comparison period
            analysis_types: Which analyses to include
            progressive: If True, only load essential data initially

        Returns:
            Formatted data for analysis template
        """
        # Determine which analyses to load
        analysis_types = self._determine_analysis_types(progressive, analysis_types)

        # Calculate date ranges
        primary_dates = self._calculate_analysis_period_dates(primary_period)
        comparison_dates = (
            self._calculate_analysis_period_dates(comparison_period) if comparison_period else None
        )

        result = {
            "period": primary_period,
            "comparison_period": comparison_period,
            "analyses": {},
            "progressive_loading": progressive,
            "dates": {
                "primary": {
                    "start": primary_dates[0].isoformat(),
                    "end": primary_dates[1].isoformat(),
                },
            },
        }

        if comparison_dates:
            result["dates"]["comparison"] = {
                "start": comparison_dates[0].isoformat(),
                "end": comparison_dates[1].isoformat(),
            }

        # Use asyncio.gather for parallel execution with proper database configuration
        import asyncio
        import logging

        logger = logging.getLogger(__name__)

        # Build tasks dictionary
        tasks = self._build_analysis_tasks(
            analysis_types, primary_dates, comparison_dates, primary_period
        )

        # Execute all tasks in parallel
        if tasks:
            import time

            start_time = time.time()
            logger.info(f"Starting parallel execution of {len(tasks)} analytics tasks")

            try:
                task_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                elapsed = time.time() - start_time
                logger.info(f"Parallel execution completed in {elapsed:.2f} seconds")

                # Map results back to task names
                task_names = list(tasks.keys())
                results_dict = {}

                for name, result_data in zip(task_names, task_results, strict=False):
                    if isinstance(result_data, Exception):
                        logger.error(f"Error in {name} analysis: {result_data}")
                        continue
                    results_dict[name] = result_data

                # Format the results
                self._format_analysis_results(result, results_dict)

                if "summary" in results_dict:
                    result["summary"] = results_dict["summary"]

            except Exception as e:
                logger.error(f"Failed to execute parallel analytics: {e}")
                # Fall back to empty results
                result["analyses"] = {}
                result["summary"] = {}

        return result

    def _determine_analysis_types(
        self, progressive: bool, analysis_types: list[str] | None
    ) -> list[str]:
        """Determine which analysis types to load based on settings."""
        if progressive:
            return ["diversity", "summary"]
        else:
            return analysis_types or [
                "diversity",
                "accumulation",
                "similarity",
                "beta",
                "weather",
                "patterns",
            ]

    def _build_analysis_tasks(
        self,
        analysis_types: list[str],
        primary_dates: tuple,
        comparison_dates: tuple | None,
        primary_period: str,
    ) -> dict:
        """Build dictionary of analysis tasks to run in parallel."""
        tasks = {}

        # Diversity timeline task
        if "diversity" in analysis_types:
            tasks["diversity"] = self.analytics_manager.calculate_diversity_timeline(
                start_date=primary_dates[0],
                end_date=primary_dates[1],
                temporal_resolution=self._get_resolution_for_period(primary_period),
            )
            # Add comparison task if requested
            if comparison_dates:
                tasks["diversity_comparison"] = self.analytics_manager.compare_period_diversity(
                    period1=primary_dates, period2=comparison_dates
                )

        # Species accumulation task
        if "accumulation" in analysis_types:
            tasks["accumulation"] = self.analytics_manager.calculate_species_accumulation(
                start_date=primary_dates[0], end_date=primary_dates[1], method="collector"
            )

        # Community similarity matrix task
        if "similarity" in analysis_types:
            periods = self._generate_similarity_periods(primary_dates[0], primary_dates[1])
            tasks["similarity"] = self.analytics_manager.calculate_community_similarity(
                periods=periods, index_type="jaccard"
            )
            # Store periods separately (not in tasks since it's not async)
            self._similarity_periods_cache = periods

        # Beta diversity task
        if "beta" in analysis_types:
            window_size = self._get_window_size_for_period(primary_period)
            tasks["beta"] = self.analytics_manager.calculate_beta_diversity(
                start_date=primary_dates[0], end_date=primary_dates[1], window_size=window_size
            )

        # Weather correlations task
        if "weather" in analysis_types:
            tasks["weather"] = self.analytics_manager.get_weather_correlation_data(
                start_date=primary_dates[0], end_date=primary_dates[1]
            )

        # Pattern analyses tasks
        if "patterns" in analysis_types:
            tasks["temporal"] = self.analytics_manager.get_temporal_patterns()
            # Add heatmap data based on period
            days = (primary_dates[1] - primary_dates[0]).days
            tasks["heatmap"] = self.analytics_manager.get_weekly_heatmap_data(days=days)

        # Summary statistics task
        tasks["summary"] = self._generate_analysis_summary(primary_dates, comparison_dates)

        return tasks

    def _format_analysis_results(self, result: dict, results_dict: dict) -> None:
        """Format analysis results and add them to the result dictionary."""
        # Diversity results
        if "diversity" in results_dict:
            result["analyses"]["diversity"] = self._format_diversity_timeline(
                results_dict["diversity"]
            )

        if "diversity_comparison" in results_dict:
            result["analyses"]["diversity_comparison"] = self._format_diversity_comparison(
                results_dict["diversity_comparison"]
            )

        # Accumulation results
        if "accumulation" in results_dict:
            result["analyses"]["accumulation"] = self._format_accumulation_curve(
                results_dict["accumulation"]
            )

        # Similarity results
        if "similarity" in results_dict:
            # Use the cached periods (not from results_dict)
            periods = getattr(self, "_similarity_periods_cache", [])
            result["analyses"]["similarity"] = self._format_similarity_matrix(
                results_dict["similarity"], periods=periods
            )

        # Beta diversity results
        if "beta" in results_dict:
            result["analyses"]["beta_diversity"] = self._format_beta_diversity(results_dict["beta"])

        # Weather results
        if "weather" in results_dict:
            result["analyses"]["weather"] = self._format_weather_correlations(
                results_dict["weather"]
            )

        # Temporal patterns results
        if "temporal" in results_dict:
            temporal = results_dict["temporal"]
            result["analyses"]["temporal_patterns"] = {
                "hourly": temporal["hourly_distribution"],
                "peak_hour": temporal["peak_hour"],
                "periods": temporal["periods"],
            }

        # Add heatmap data if available
        if "heatmap" in results_dict:
            if "temporal_patterns" not in result["analyses"]:
                result["analyses"]["temporal_patterns"] = {}
            result["analyses"]["temporal_patterns"]["heatmap"] = results_dict["heatmap"]

    # === FORMATTING METHODS ===

    def _format_diversity_timeline(self, data: list[dict]) -> dict:
        """Format diversity metrics for timeline visualization."""
        return {
            "periods": [d["period"] for d in data],
            "shannon": [d["shannon"] for d in data],
            "simpson": [d["simpson"] for d in data],
            "richness": [d["richness"] for d in data],
            "evenness": [d["evenness"] for d in data],
            "total_detections": [d["total_detections"] for d in data],
        }

    def _format_diversity_comparison(self, data: dict) -> dict:
        """Format diversity comparison for display."""

        def format_change(value: float) -> dict:
            return {
                "value": round(value, 3),
                "trend": "up" if value > 0 else "down" if value < 0 else "stable",
                "significant": abs(value) > 0.1,  # Threshold for significance
            }

        return {
            "period1_metrics": data["period1"],
            "period2_metrics": data["period2"],
            "changes": {key: format_change(value) for key, value in data["changes"].items()},
        }

    def _format_accumulation_curve(self, data: dict) -> dict:
        """Format accumulation curve for visualization."""
        return {
            "samples": data["samples"],
            "species_counts": data["species_counts"],
            "method": data["method"],
            "total_samples": len(data["samples"]),
            "total_species": max(data["species_counts"]) if data["species_counts"] else 0,
        }

    def _format_similarity_matrix(self, data: dict, periods: list | None = None) -> dict:
        """Format similarity matrix for heatmap display."""
        matrix = data["matrix"]
        labels = data["labels"]

        # Create better labels with date ranges if periods are provided
        if periods:
            formatted_labels = []
            for _i, (start, end) in enumerate(periods):
                # Calculate period duration
                duration = (end - start).days
                if duration == 1:
                    # Single day - show date
                    label = start.strftime("%b %d")
                elif duration <= 7:
                    # Week or less - show date range
                    label = f"{start.strftime('%b %d')}-{end.strftime('%d')}"
                else:
                    # Longer period - show month and dates
                    label = f"{start.strftime('%b %d')} - {end.strftime('%b %d')}"
                formatted_labels.append(label)

            # Add period size information
            period_days = (periods[0][1] - periods[0][0]).days if periods else 0
            period_info = {
                "count": len(periods),
                "size_days": period_days,
                "total_days": (periods[-1][1] - periods[0][0]).days if periods else 0,
            }
        else:
            formatted_labels = labels
            period_info = None

        # Convert to percentage and threshold for display
        formatted_matrix = []
        for row in matrix:
            formatted_row = [
                {
                    "value": round(val * 100, 1),
                    "display": f"{round(val * 100)}" if val > 0.5 else "",
                    "intensity": self._get_intensity_class(val),
                }
                for val in row
            ]
            formatted_matrix.append(formatted_row)

        return {
            "labels": formatted_labels,
            "matrix": formatted_matrix,
            "index_type": data["index_type"],
            "period_info": period_info,
        }

    def _format_beta_diversity(self, data: list[dict]) -> dict:
        """Format beta diversity for visualization."""
        return {
            "periods": [d["period_start"] for d in data],
            "turnover_rates": [d["turnover_rate"] for d in data],
            "species_gained": [d["species_gained"] for d in data],
            "species_lost": [d["species_lost"] for d in data],
            "total_species": [d["total_species"] for d in data],
        }

    def _format_weather_correlations(self, data: dict) -> dict:
        """Format weather correlation data for scatter plots."""
        # Calculate correlation coefficients if data available
        correlations = {}
        if data["detection_counts"] and data["temperature"]:
            # Use AnalyticsManager for correlation calculations
            correlations = {
                "temperature": self.analytics_manager.calculate_correlation(
                    data["detection_counts"], data["temperature"]
                ),
                "humidity": self.analytics_manager.calculate_correlation(
                    data["detection_counts"], data["humidity"]
                ),
                "wind_speed": self.analytics_manager.calculate_correlation(
                    data["detection_counts"], data["wind_speed"]
                ),
            }

        return {
            "hours": data["hours"],
            "detection_counts": data["detection_counts"],
            "weather_variables": {
                "temperature": data["temperature"],
                "humidity": data["humidity"],
                "wind_speed": data["wind_speed"],
                "precipitation": data["precipitation"],
            },
            "correlations": correlations,
        }

    # === HELPER METHODS ===

    def _calculate_analysis_period_dates(self, period: str) -> tuple[datetime, datetime]:
        """Calculate start and end dates for analysis period."""
        now = datetime.now(UTC)

        # Handle both formats: "7d" style and "week" style
        period_mapping = {
            "24h": "day",  # Handle 24-hour format
            "1d": "day",
            "7d": "week",
            "30d": "month",
            "90d": "season",
            "365d": "year",
            "day": "day",
            "week": "week",
            "month": "month",
            "season": "season",
            "year": "year",
        }

        normalized_period = period_mapping.get(period, "day")

        periods = {
            "day": (now - timedelta(days=1), now),
            "week": (now - timedelta(days=7), now),
            "month": (now - timedelta(days=30), now),
            "season": (now - timedelta(days=90), now),
            "year": (now - timedelta(days=365), now),
        }

        return periods.get(normalized_period, periods["day"])

    def _get_resolution_for_period(self, period: str) -> str:
        """Get appropriate temporal resolution for period."""
        # Normalize period format
        period_mapping = {
            "24h": "day",
            "1d": "day",
            "7d": "week",
            "30d": "month",
            "90d": "season",
            "365d": "year",
            "day": "day",
            "week": "week",
            "month": "month",
            "season": "season",
            "year": "year",
        }
        normalized_period = period_mapping.get(period, "day")

        resolutions = {
            "day": "hourly",
            "week": "daily",
            "month": "daily",
            "season": "weekly",
            "year": "weekly",
        }
        return resolutions.get(normalized_period, "daily")

    def _get_window_size_for_period(self, period: str) -> timedelta:
        """Get appropriate window size for beta diversity."""
        # Normalize period format
        period_mapping = {
            "24h": "day",
            "1d": "day",
            "7d": "week",
            "30d": "month",
            "90d": "season",
            "365d": "year",
            "day": "day",
            "week": "week",
            "month": "month",
            "season": "season",
            "year": "year",
        }
        normalized_period = period_mapping.get(period, "day")

        windows = {
            "day": timedelta(hours=6),
            "week": timedelta(days=1),
            "month": timedelta(days=5),
            "season": timedelta(days=15),
            "year": timedelta(days=60),
        }
        return windows.get(normalized_period, timedelta(days=1))

    def _get_days_for_period(self, period: str) -> int:
        """Get number of days for the period."""
        # Normalize period format
        period_mapping = {
            "24h": "day",
            "1d": "day",
            "7d": "week",
            "30d": "month",
            "90d": "season",
            "365d": "year",
            "day": "day",
            "week": "week",
            "month": "month",
            "season": "season",
            "year": "year",
        }
        normalized_period = period_mapping.get(period, "day")

        days = {"day": 1, "week": 7, "month": 30, "season": 90, "year": 365}
        return days.get(normalized_period, 7)

    def _get_intensity_class(self, value: float) -> str:
        """Get CSS class for intensity coloring."""
        if value >= 0.8:
            return "very-high"
        elif value >= 0.6:
            return "high"
        elif value >= 0.4:
            return "medium"
        elif value >= 0.2:
            return "low"
        else:
            return "very-low"

    def _generate_similarity_periods(
        self, start_date: datetime, end_date: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Generate time periods for similarity analysis."""
        total_duration = end_date - start_date
        n_periods = min(6, max(2, int(total_duration.days / 7)))  # 2-6 periods

        period_duration = total_duration / n_periods
        periods = []

        for i in range(n_periods):
            period_start = start_date + (period_duration * i)
            period_end = start_date + (period_duration * (i + 1))
            periods.append((period_start, period_end))

        return periods

    async def _generate_analysis_summary(
        self,
        primary_dates: tuple[datetime, datetime],
        comparison_dates: tuple[datetime, datetime] | None,
    ) -> dict:
        """Generate summary statistics for the analysis page."""
        # Get basic metrics for primary period
        primary_summary = await self.analytics_manager.get_dashboard_summary()

        summary = {
            "primary_period": {
                "start": primary_dates[0].isoformat(),
                "end": primary_dates[1].isoformat(),
                "total_species": primary_summary["species_total"],
                "total_detections": primary_summary[
                    "detections_today"
                ],  # Would need period-specific
            }
        }

        if comparison_dates:
            # Would need to implement period-specific summary
            summary["comparison_period"] = {
                "start": comparison_dates[0].isoformat(),
                "end": comparison_dates[1].isoformat(),
                "total_species": 0,  # Placeholder
                "total_detections": 0,  # Placeholder
            }

        return summary
