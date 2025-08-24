import time
from collections.abc import Sequence
from datetime import datetime
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
from birdnetpi.system.status import SystemInspector

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
    count: int


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


class CPUStatus(BaseModel):
    """CPU status metrics."""

    percent: float
    temp: float


class MemoryStatus(BaseModel):
    """Memory status metrics."""

    percent: float
    used_gb: float
    total_gb: float


class DiskStatus(BaseModel):
    """Disk status metrics."""

    percent: float
    used_gb: float
    total_gb: float


class AudioStatus(BaseModel):
    """Audio device status."""

    level_db: int
    device: str


class SystemStatusDict(BaseModel):
    """System status data."""

    cpu: CPUStatus
    memory: MemoryStatus
    disk: DiskStatus
    audio: AudioStatus
    uptime: str


class LandingPageData(BaseModel):
    """Complete landing page data."""

    metrics: MetricsDict
    detection_log: list[DetectionLogEntry]
    species_frequency: list[SpeciesListEntry]
    hourly_distribution: list[int]
    visualization_data: list[ScatterDataPoint]
    system_status: SystemStatusDict


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

    def __init__(self, analytics_manager: AnalyticsManager, config: BirdNETConfig):
        self.analytics_manager = analytics_manager
        self.config = config

    # --- Landing Page ---

    async def get_landing_page_data(self) -> LandingPageData:
        """Format all data needed for landing page."""
        summary = await self.analytics_manager.get_dashboard_summary()
        frequency = await self.analytics_manager.get_species_frequency_analysis()
        temporal = await self.analytics_manager.get_temporal_patterns()
        recent = await self.analytics_manager.data_manager.get_recent_detections(10)
        scatter = await self.analytics_manager.get_detection_scatter_data()

        return LandingPageData(
            metrics=self._format_metrics(summary),
            detection_log=self._format_detection_log(recent),
            species_frequency=self._format_species_list(frequency[:12]),
            hourly_distribution=temporal["hourly_distribution"],
            visualization_data=self._format_scatter_data(scatter),
            system_status=self._get_system_status(),  # Runtime data
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
                count=1,  # Or aggregate if needed
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

    def _get_system_status(self) -> SystemStatusDict:
        """Get runtime system metrics."""
        cpu_percent = SystemInspector.get_cpu_usage()
        cpu_temp = SystemInspector.get_cpu_temperature()
        memory_info = SystemInspector.get_memory_usage()
        disk_info = SystemInspector.get_disk_usage("/")
        system_info = SystemInspector.get_system_info()

        # Calculate uptime from boot time
        boot_time = system_info.get("boot_time", time.time())
        uptime_seconds = time.time() - boot_time
        uptime_days = int(uptime_seconds // 86400)

        return SystemStatusDict(
            cpu=CPUStatus(percent=cpu_percent, temp=cpu_temp if cpu_temp is not None else 0),
            memory=MemoryStatus(
                percent=memory_info["percent"],
                used_gb=memory_info["used"] / (1024**3),
                total_gb=memory_info["total"] / (1024**3),
            ),
            disk=DiskStatus(
                percent=disk_info["percent"],
                used_gb=disk_info["used"] / (1024**3),
                total_gb=disk_info["total"] / (1024**3),
            ),
            audio=AudioStatus(
                level_db=-42,  # Would come from audio monitoring
                device="USB Audio Device",  # TODO: Get from audio device service
            ),
            uptime=f"{uptime_days}d",
        )

    # --- API Responses ---

    def format_api_response(self, data: T, status: str = "success") -> APIResponse[T]:
        """Format data for API response."""
        return APIResponse(status=status, timestamp=datetime.now().isoformat(), data=data)
