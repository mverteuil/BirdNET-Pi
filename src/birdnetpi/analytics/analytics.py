from datetime import date, datetime, timedelta
from typing import TypedDict

from birdnetpi.config import BirdNETConfig
from birdnetpi.detections.data_manager import DataManager


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
    """Performs calculations and analysis on raw data using DataManager methods."""

    def __init__(self, data_manager: DataManager, config: BirdNETConfig):
        self.data_manager = data_manager
        self.config = config

    # --- Dashboard Analytics ---

    async def get_dashboard_summary(self) -> DashboardSummaryDict:
        """Calculate summary statistics for dashboard."""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        # Get counts using the new DataManager methods
        detections_today = await self.data_manager.get_detection_count(today_start, now)
        species_total = await self.data_manager.get_unique_species_count(
            datetime.min.replace(tzinfo=None), now
        )
        species_week = await self.data_manager.get_unique_species_count(week_ago, now)

        # Get storage metrics
        storage = await self.data_manager.get_storage_metrics()

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
        species_counts = await self.data_manager.get_species_counts(start_time, end_time)

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
        hourly_data = await self.data_manager.get_hourly_counts(date)

        # Create 24-hour array with counts
        hourly_dist = [0] * 24
        for item in hourly_data:
            hour = item["hour"]
            hourly_dist[hour] = item["count"]

        # Identify peak periods
        max_count = max(hourly_dist) if hourly_dist else 0
        peak_hour = hourly_dist.index(max_count) if max_count > 0 else None

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

        # Get detections in time range from DataManager
        detections = await self.data_manager.get_detections_in_range(start_time, end_time)

        # Group by species for frequency classification
        species_counts = {}
        for d in detections:
            species_name = d.common_name or d.scientific_name
            if species_name:
                species_counts[species_name] = species_counts.get(species_name, 0) + 1

        return [
            {
                "time": d.timestamp.hour + (d.timestamp.minute / 60),
                "confidence": d.confidence,
                "species": d.common_name or d.scientific_name,
                "frequency_category": self._categorize_frequency(
                    species_counts.get(d.common_name or d.scientific_name, 0)
                ),
            }
            for d in detections
            if d.timestamp
        ]

    @staticmethod
    def _categorize_frequency(count: int) -> str:
        """Categorize species by detection frequency."""
        if count > 200:
            return "common"
        elif count > 50:
            return "regular"
        else:
            return "uncommon"
