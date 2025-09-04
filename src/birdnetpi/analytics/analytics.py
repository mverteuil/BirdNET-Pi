from datetime import date, datetime, timedelta
from typing import TypedDict

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.queries import DetectionQueryService


class DashboardSummaryDict(TypedDict):
    """Dashboard summary statistics."""

    species_total: int
    detections_today: int
    species_week: int
    storage_gb: float
    hours_monitored: float
    confidence_threshold: float


class SpeciesFrequencyDict(TypedDict):
    """Species frequency analysis result."""

    name: str
    count: int
    percentage: float
    category: str


class TemporalPatternsDict(TypedDict):
    """Temporal pattern analysis result."""

    hourly_distribution: list[int]
    peak_hour: int | None
    periods: dict[str, int]


class ScatterDataDict(TypedDict):
    """Scatter plot data point."""

    time: float
    confidence: float
    species: str
    frequency_category: str


class AnalyticsManager:
    """Performs calculations and analysis on raw data using DetectionQueryService methods."""

    def __init__(self, detection_query_service: DetectionQueryService, config: BirdNETConfig):
        self.detection_query_service = detection_query_service
        self.config = config

    # --- Dashboard Analytics ---

    async def get_dashboard_summary(self) -> DashboardSummaryDict:
        """Calculate summary statistics for dashboard."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        # Get counts using the new DataManager methods
        detections_today = await self.detection_query_service.get_detection_count(today_start, now)
        species_total = await self.detection_query_service.get_unique_species_count(
            datetime.min.replace(tzinfo=None), now
        )
        species_week = await self.detection_query_service.get_unique_species_count(week_ago, now)

        # Get storage metrics
        storage = await self.detection_query_service.get_storage_metrics()

        return {
            "species_total": species_total,
            "detections_today": detections_today,
            "species_week": species_week,
            "storage_gb": storage.get("total_bytes", 0) / (1024**3),
            "hours_monitored": storage.get("total_duration", 0) / 3600,
            "confidence_threshold": self.config.species_confidence_threshold,
        }

    async def get_species_frequency_analysis(self, hours: int = 24) -> list[SpeciesFrequencyDict]:
        """Analyze species frequency distribution."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # Get species counts from DataManager
        species_counts = await self.detection_query_service.get_species_counts(start_time, end_time)

        # Calculate total for percentages
        total = sum(s["count"] for s in species_counts)

        return [
            {
                "name": s["common_name"] or s["scientific_name"],
                "count": s["count"],
                "percentage": (s["count"] / total * 100) if total > 0 else 0,
                "category": self._categorize_frequency(s["count"]),
            }
            for s in species_counts
        ]

    async def get_temporal_patterns(self, date: date | None = None) -> TemporalPatternsDict:
        """Analyze temporal detection patterns."""
        if date is None:
            date = datetime.now().date()

        # Get hourly counts from DataManager
        hourly_data = await self.detection_query_service.get_hourly_counts(date)

        # Create 24-hour array with counts
        hourly_dist = [0] * 24
        for item in hourly_data:
            hour = item["hour"]
            hourly_dist[hour] = item["count"]

        # Identify peak periods
        max_count = max(hourly_dist) if hourly_dist else 0
        # Return 6 AM as default peak hour when no detections (typical bird activity time)
        peak_hour = hourly_dist.index(max_count) if max_count > 0 else 6

        # Categorize activity periods (6 equal 4-hour periods)
        night_early = sum(hourly_dist[0:4])  # 12am-4am
        dawn = sum(hourly_dist[4:8])  # 4am-8am
        morning = sum(hourly_dist[8:12])  # 8am-12pm
        afternoon = sum(hourly_dist[12:16])  # 12pm-4pm
        evening = sum(hourly_dist[16:20])  # 4pm-8pm
        night_late = sum(hourly_dist[20:24])  # 8pm-12am

        return {
            "hourly_distribution": hourly_dist,
            "peak_hour": peak_hour,
            "periods": {
                "night_early": night_early,  # 12am-4am
                "dawn": dawn,  # 4am-8am
                "morning": morning,  # 8am-12pm
                "afternoon": afternoon,  # 12pm-4pm
                "evening": evening,  # 4pm-8pm
                "night_late": night_late,  # 8pm-12am
            },
        }

    async def get_detection_scatter_data(self, hours: int = 24) -> list[ScatterDataDict]:
        """Prepare detection data for scatter visualization."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # Get detections in time range - always returns DetectionWithTaxa
        detections = await self.detection_query_service.query_detections(
            start_date=start_time, end_date=end_time, order_by="timestamp", order_desc=True
        )

        # Group by species for frequency classification
        species_counts = {}
        for d in detections:
            # Use translated name if available, otherwise IOC name, otherwise common/scientific
            species_name = (
                d.translated_name or d.ioc_english_name or d.common_name or d.scientific_name
            )
            if species_name:
                species_counts[species_name] = species_counts.get(species_name, 0) + 1

        return [
            {
                "time": d.timestamp.hour + (d.timestamp.minute / 60),
                "confidence": d.confidence,
                "species": d.translated_name
                or d.ioc_english_name
                or d.common_name
                or d.scientific_name,
                "frequency_category": self._categorize_frequency(
                    species_counts.get(
                        d.translated_name
                        or d.ioc_english_name
                        or d.common_name
                        or d.scientific_name,
                        0,
                    )
                ),
            }
            for d in detections
            if d.timestamp
        ]

    async def get_aggregate_hourly_pattern(self, days: int = 30) -> list[list[int]]:
        """Get aggregated hourly pattern over N days for heatmap.

        For periods longer than 7 days, aggregates all data by day-of-week
        and hour to show patterns like "Mondays at 8am" across the entire period.

        Returns:
            List of lists for heatmap (7 days-of-week x 24 hours)
        """
        if days <= 7:
            # For short periods, return daily data
            return await self.get_weekly_heatmap_data(days)

        # For longer periods, aggregate by day-of-week
        # Initialize 7x24 grid (Sunday=0 to Saturday=6)
        weekday_hourly = [[0] * 24 for _ in range(7)]

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # Iterate through all days in the period
        current_date = start_date
        while current_date <= end_date:
            # Get hourly counts for this day
            hourly_data = await self.detection_query_service.get_hourly_counts(current_date)

            # Get day of week (0=Monday, 6=Sunday in Python)
            # Convert to 0=Sunday, 6=Saturday for display
            weekday = (current_date.weekday() + 1) % 7

            # Add counts to the appropriate day-of-week
            for item in hourly_data:
                hour = int(item["hour"]) if isinstance(item["hour"], str) else item["hour"]
                count = item["count"]
                weekday_hourly[weekday][hour] += count

            current_date += timedelta(days=1)

        return weekday_hourly

    async def get_weekly_heatmap_data(self, days: int = 7) -> list[list[int]]:
        """Get hourly detection counts for past N days for heatmap visualization.

        Returns:
            List of 7 lists, each with 24 hourly counts
        """
        heatmap_data = []
        end_date = datetime.now().date()

        for day_offset in range(days):
            target_date = end_date - timedelta(days=day_offset)
            hourly_data = await self.detection_query_service.get_hourly_counts(target_date)

            # Create 24-hour array with counts
            day_counts = [0] * 24
            for item in hourly_data:
                hour = item["hour"]
                day_counts[hour] = item["count"]

            # Insert at beginning to maintain chronological order
            heatmap_data.insert(0, day_counts)

        return heatmap_data

    async def get_weekly_patterns(self) -> dict[str, list[int]]:
        """Get detection patterns grouped by day of week.

        Returns:
            Dict with keys 'sun', 'mon', etc. and hourly count arrays
        """
        from collections import defaultdict

        # Get past 28 days to have multiple samples per weekday
        days_to_analyze = 28
        end_date = datetime.now().date()

        # Aggregate by weekday
        weekday_patterns = defaultdict(lambda: [0] * 24)
        weekday_counts = defaultdict(int)

        for day_offset in range(days_to_analyze):
            target_date = end_date - timedelta(days=day_offset)
            weekday = target_date.weekday()  # 0=Monday, 6=Sunday

            hourly_data = await self.detection_query_service.get_hourly_counts(target_date)
            weekday_counts[weekday] += 1

            for item in hourly_data:
                hour = item["hour"]
                weekday_patterns[weekday][hour] += item["count"]

        # Average the counts and format for display
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        result = {}

        for day_num, day_name in enumerate(day_names):
            if weekday_counts[day_num] > 0:
                # Average the counts
                avg_pattern = [
                    count // weekday_counts[day_num] for count in weekday_patterns[day_num]
                ]
                result[day_name] = avg_pattern
            else:
                result[day_name] = [0] * 24

        # Rearrange to start with Sunday
        result = {
            "sun": result["sun"],
            "mon": result["mon"],
            "tue": result["tue"],
            "wed": result["wed"],
            "thu": result["thu"],
            "fri": result["fri"],
            "sat": result["sat"],
        }

        return result

    async def get_detection_frequency_distribution(self, days: int = 7) -> list[dict[str, str]]:
        """Get stem-and-leaf plot data for detection frequency distribution.

        Returns:
            List of dicts with 'stem' and 'leaves' for display
        """
        from collections import defaultdict

        # Collect all hourly counts for the period
        hourly_counts = []
        end_date = datetime.now().date()

        for day_offset in range(days):
            target_date = end_date - timedelta(days=day_offset)
            hourly_data = await self.detection_query_service.get_hourly_counts(target_date)

            for item in hourly_data:
                if item["count"] > 0:
                    hourly_counts.append(item["count"])

        if not hourly_counts:
            return [{"stem": "0", "leaves": "No data"}]

        # Create stem-and-leaf structure
        stem_leaf = defaultdict(list)
        for count in sorted(hourly_counts):
            stem = count // 10
            leaf = count % 10
            stem_leaf[stem].append(str(leaf))

        # Format for display
        result = []
        for stem in sorted(stem_leaf.keys()):
            result.append({"stem": str(stem), "leaves": " ".join(stem_leaf[stem])})

        return result

    async def get_species_hourly_patterns(self, species_name: str, days: int = 7) -> list[int]:
        """Get hourly detection pattern for a specific species.

        Args:
            species_name: Scientific or common name of species
            days: Number of days to analyze

        Returns:
            List of 24 hourly counts totaled over the period
        """
        hourly_totals = [0] * 24
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        # Get all detections for this species in the range - always returns DetectionWithTaxa
        detections = await self.detection_query_service.query_detections(
            start_date=start_time, end_date=end_time, order_by="timestamp", order_desc=True
        )

        # Filter for the species and aggregate by hour
        for d in detections:
            # Check against all name variants (scientific, common, IOC, translated)
            if (
                d.scientific_name == species_name
                or d.common_name == species_name
                or d.ioc_english_name == species_name
                or d.translated_name == species_name
            ):
                hour = d.timestamp.hour if d.timestamp else 0
                hourly_totals[hour] += 1

        # Return raw counts, not averaged (sparklines show patterns, not averages)
        return hourly_totals

    @staticmethod
    def _categorize_frequency(count: int) -> str:
        """Categorize species by detection frequency.

        Thresholds are calibrated for 24-hour periods:
        - Common: More than 20 detections (frequent visitor)
        - Regular: 6-20 detections (occasional visitor)
        - Uncommon: 5 or fewer detections (rare sighting)
        """
        if count > 20:
            return "common"
        elif count > 5:
            return "regular"
        else:
            return "uncommon"
