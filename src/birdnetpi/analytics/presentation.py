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
)
from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.models import DetectionBase
from birdnetpi.detections.queries import DetectionQueryService

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
    ):
        self.analytics_manager = analytics_manager
        self.detection_query_service = detection_query_service
        self.config = config

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
            species_frequency=self._format_species_list(frequency[:12]),
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
            # Extract name from dict or object
            if isinstance(species, dict):
                name = (
                    species.get("translated_name", None)
                    or species.get("best_common_name", None)
                    or species.get("common_name", None)
                    or species.get("scientific_name", "Unknown")
                )
                count = species.get("detection_count", species.get("count", 0))
            else:
                name = (
                    getattr(species, "translated_name", None)
                    or getattr(species, "best_common_name", None)
                    or getattr(species, "common_name", None)
                    or getattr(species, "scientific_name", "Unknown")
                )
                count = getattr(species, "count", 0)

            species_frequency.append(
                {
                    "name": name,
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

    async def _get_heatmap_data(self, period: str) -> tuple[list, str]:
        """Get heatmap data and title for the given period.

        Args:
            period: Current period for display

        Returns:
            Tuple of (heatmap_data, heatmap_title)
        """
        if period in ["day", "week"]:
            # For day/week views, show past 7 days hourly pattern
            heatmap_data = await self.analytics_manager.get_weekly_heatmap_data(7)
            heatmap_title = "24-Hour Activity Pattern (Past 7 Days)"
        else:
            # For longer periods, use aggregate method that groups by week
            period_days = {
                "month": 30,
                "season": 90,
                "year": 365,
                "historical": 3650,  # ~10 years
            }
            days_for_heatmap = period_days.get(period, 30)

            # Use aggregate method for longer periods (returns weekly aggregates)
            heatmap_data = await self.analytics_manager.get_aggregate_hourly_pattern(
                days_for_heatmap
            )

            # Format the title based on period
            period_labels = {
                "month": "Past Month",
                "season": "Past Season",
                "year": "Past Year",
                "historical": "All Time",
            }
            period_label = period_labels.get(period, "Selected Period")
            heatmap_title = f"24-Hour Activity Pattern by Day of Week ({period_label})"

        return heatmap_data, heatmap_title

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
        # Calculate time ranges based on period
        start_date, period_label = self._calculate_period_range(period)

        # For display, use the current time in UTC
        now = datetime.now(UTC)

        # Get detections with localization if service is available
        # We'll load detections via AJAX, so just provide empty list initially
        recent_detections = []

        # Get species summary from appropriate source
        species_summary = await self._get_species_summary_data(detection_query_service, start_date)

        # Get analytics data
        temporal_patterns = await self.analytics_manager.get_temporal_patterns(
            date=now.date() if period == "day" else None
        )
        dashboard_summary = await self.analytics_manager.get_dashboard_summary()

        # Format species frequency table
        species_frequency = self._format_species_frequency(species_summary, period)

        # Format top species for sparklines
        top_species = self._format_top_species(species_summary)

        # Generate sparkline data with real species-specific patterns for the selected period
        sparkline_data = await self._generate_sparkline_data(top_species, period)

        # Get real weekly patterns from analytics
        weekly_data = await self.analytics_manager.get_weekly_patterns()

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

        # Use real weekly patterns for charts
        # Sample every 2-3 hours for mini charts (10 points)
        week_patterns_data = {}
        sample_hours = [0, 3, 6, 8, 10, 12, 14, 16, 18, 21]  # 10 representative hours

        for day in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]:
            day_pattern = weekly_data.get(day, [0] * 24)
            sampled_pattern = [day_pattern[h] if h < len(day_pattern) else 0 for h in sample_hours]
            week_patterns_data[f"{day}-chart"] = sampled_pattern

        # Get heatmap data appropriate for the selected period
        heatmap_data, heatmap_title = await self._get_heatmap_data(period)

        # Calculate statistics based on the actual species summary data
        period_species = len(species_frequency) if species_frequency else 0
        period_detections = (
            sum(s.get("count", 0) for s in species_frequency) if species_frequency else 0
        )

        # Find peak activity time from temporal patterns
        peak_hour = temporal_patterns.get("peak_hour") or 6
        peak_detections = temporal_patterns["hourly_distribution"][peak_hour] if peak_hour else 0
        peak_activity_time = f"{peak_hour:02d}:00-{(peak_hour + 1):02d}:00"

        # Get new species this week (simplified - would need historical comparison)
        new_species = []
        if species_summary and len(species_summary) > 0:
            # Take the most recently detected rare species as "new"
            for species in species_summary[-3:]:
                if isinstance(species, dict):
                    name = species.get("common_name") or species.get("scientific_name")
                    if name and species.get("detection_count", 0) < 5:
                        new_species.append(name)

        trend_percentage = 18  # Would calculate from historical data

        return {
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
            "trend_symbol": "↑" if trend_percentage > 0 else "↓" if trend_percentage < 0 else "→",
            "trend_percentage": abs(trend_percentage),
            # Main data
            "recent_detections": recent_detections,
            "species_frequency": species_frequency,
            "top_species": top_species,
            "weekly_patterns": weekly_patterns,
            # Chart data
            "sparkline_data": sparkline_data,
            "week_patterns_data": week_patterns_data,
            "heatmap_data": heatmap_data,
            "heatmap_title": heatmap_title,
            # Configuration
            "period": period,  # Pass current period for template highlighting
            "confidence_threshold": self.config.species_confidence_threshold,
            "migration_note": "Migration period may affect species diversity through October."
            if 8 <= now.month <= 10
            else None,
        }

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
    ) -> dict:
        """Format comprehensive analysis page data.

        Args:
            primary_period: Main period to analyze ("day", "week", "month", "season", "year")
            comparison_period: Optional comparison period
            analysis_types: Which analyses to include

        Returns:
            Formatted data for analysis template
        """
        analysis_types = analysis_types or [
            "diversity",
            "accumulation",
            "similarity",
            "beta",
            "weather",
            "patterns",
        ]

        # Calculate date ranges
        primary_dates = self._calculate_analysis_period_dates(primary_period)
        comparison_dates = (
            self._calculate_analysis_period_dates(comparison_period) if comparison_period else None
        )

        result = {"period": primary_period, "comparison_period": comparison_period, "analyses": {}}

        # Get diversity timeline
        if "diversity" in analysis_types:
            diversity_data = await self.analytics_manager.calculate_diversity_timeline(
                start_date=primary_dates[0],
                end_date=primary_dates[1],
                temporal_resolution=self._get_resolution_for_period(primary_period),
            )
            result["analyses"]["diversity"] = self._format_diversity_timeline(diversity_data)

            # Add comparison if requested
            if comparison_dates:
                comparison_diversity = await self.analytics_manager.compare_period_diversity(
                    period1=primary_dates, period2=comparison_dates
                )
                result["analyses"]["diversity_comparison"] = self._format_diversity_comparison(
                    comparison_diversity
                )

        # Get species accumulation
        if "accumulation" in analysis_types:
            accumulation_data = await self.analytics_manager.calculate_species_accumulation(
                start_date=primary_dates[0], end_date=primary_dates[1], method="collector"
            )
            result["analyses"]["accumulation"] = self._format_accumulation_curve(accumulation_data)

        # Get community similarity matrix
        if "similarity" in analysis_types:
            # Create time windows for similarity analysis
            periods = self._generate_similarity_periods(primary_dates[0], primary_dates[1])
            similarity_data = await self.analytics_manager.calculate_community_similarity(
                periods=periods, index_type="jaccard"
            )
            result["analyses"]["similarity"] = self._format_similarity_matrix(similarity_data)

        # Get beta diversity
        if "beta" in analysis_types:
            window_size = self._get_window_size_for_period(primary_period)
            beta_data = await self.analytics_manager.calculate_beta_diversity(
                start_date=primary_dates[0], end_date=primary_dates[1], window_size=window_size
            )
            result["analyses"]["beta_diversity"] = self._format_beta_diversity(beta_data)

        # Get weather correlations
        if "weather" in analysis_types:
            weather_data = await self.analytics_manager.get_weather_correlation_data(
                start_date=primary_dates[0], end_date=primary_dates[1]
            )
            result["analyses"]["weather"] = self._format_weather_correlations(weather_data)

        # Get existing pattern analyses
        if "patterns" in analysis_types:
            # Use existing methods for temporal patterns
            temporal = await self.analytics_manager.get_temporal_patterns()
            heatmap = await self.analytics_manager.get_aggregate_hourly_pattern(
                days=self._get_days_for_period(primary_period)
            )

            result["analyses"]["temporal_patterns"] = {
                "hourly": temporal["hourly_distribution"],
                "peak_hour": temporal["peak_hour"],
                "periods": temporal["periods"],
                "heatmap": heatmap,
            }

        # Add summary statistics
        result["summary"] = await self._generate_analysis_summary(primary_dates, comparison_dates)

        return result

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

    def _format_similarity_matrix(self, data: dict) -> dict:
        """Format similarity matrix for heatmap display."""
        matrix = data["matrix"]
        labels = data["labels"]

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

        return {"labels": labels, "matrix": formatted_matrix, "index_type": data["index_type"]}

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

        periods = {
            "day": (now - timedelta(days=1), now),
            "week": (now - timedelta(days=7), now),
            "month": (now - timedelta(days=30), now),
            "season": (now - timedelta(days=90), now),
            "year": (now - timedelta(days=365), now),
        }

        return periods.get(period, periods["day"])

    def _get_resolution_for_period(self, period: str) -> str:
        """Get appropriate temporal resolution for period."""
        resolutions = {
            "day": "hourly",
            "week": "daily",
            "month": "daily",
            "season": "weekly",
            "year": "weekly",
        }
        return resolutions.get(period, "daily")

    def _get_window_size_for_period(self, period: str) -> timedelta:
        """Get appropriate window size for beta diversity."""
        windows = {
            "day": timedelta(hours=6),
            "week": timedelta(days=1),
            "month": timedelta(days=7),
            "season": timedelta(days=14),
            "year": timedelta(days=30),
        }
        return windows.get(period, timedelta(days=1))

    def _get_days_for_period(self, period: str) -> int:
        """Get number of days for the period."""
        days = {"day": 1, "week": 7, "month": 30, "season": 90, "year": 365}
        return days.get(period, 7)

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
