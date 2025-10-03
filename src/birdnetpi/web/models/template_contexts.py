"""Pydantic models for template context validation.

These models define the required and optional context variables for each template,
providing type safety and early detection of missing variables.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from birdnetpi.audio.devices import AudioDevice
from birdnetpi.config.models import BirdNETConfig
from birdnetpi.web.models.logs import LogLevelInfo
from birdnetpi.web.models.update import UpdateActionResponse, UpdateStatusResponse


class BaseTemplateContext(BaseModel):
    """Base context required by base.html.j2 template.

    All page templates must provide at least these variables.
    """

    # Required by base template
    config: BirdNETConfig = Field(
        ..., description="Application configuration (used throughout base template)"
    )
    system_status: dict[str, Any] = Field(
        ..., description="System status dict with 'device_name' key"
    )
    language: str = Field(
        "en", description="User's preferred language code (from Accept-Language header)"
    )

    # Optional - set by child templates
    page_name: str | None = Field(default=None, description="Page title to display in header")
    active_page: str = Field(default="", description="Active navigation item identifier")
    model_update_date: str | None = Field(
        default=None, description="Date of last model update (for footer)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_serializer("config")
    def serialize_config(
        self,
        config: BirdNETConfig,
        _info: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        """Serialize config to dict for template access via config['key']."""
        return config.model_dump()


class DetectionsPageContext(BaseTemplateContext):
    """Context for reports/all_detections.html.j2 template.

    Uses progressive loading - data is fetched client-side via JavaScript.
    """

    # Required by detections page
    period: str = Field(..., description="Time period filter (day/week/month/etc)")

    # Optional error state
    error: str | None = Field(default=None, description="Error message if page failed to load")


class AnalysisPageContext(BaseTemplateContext):
    """Context for reports/analysis.html.j2 template.

    Uses progressive loading - data is fetched client-side via JavaScript.
    """

    # Required by analysis page
    period: str = Field(..., description="Analysis period (30d/month/year/etc)")
    comparison_period: str | None = Field(
        default=None, description="Comparison period for change analysis"
    )


class BestRecordingsPageContext(BaseTemplateContext):
    """Context for reports/best_recordings.html.j2 template."""

    # Required by best recordings page
    detections: list[Any] = Field(..., description="High-confidence detections")
    avg_confidence: float = Field(..., description="Average confidence score")
    date_range: str = Field(..., description="Date range of recordings")
    total_species: int = Field(..., description="Number of unique species")

    # Optional error state
    error: str | None = Field(default=None, description="Error message if page failed to load")


class LivestreamPageContext(BaseTemplateContext):
    """Context for admin/livestream.html.j2 template."""

    # No additional fields required - uses only base template fields
    pass


class LogsPageContext(BaseTemplateContext):
    """Context for admin/logs.html.j2 template."""

    services: list[dict[str, Any]] = Field(..., description="List of service configurations")
    log_levels: list[LogLevelInfo] = Field(..., description="Available log levels")


class ServicesPageContext(BaseTemplateContext):
    """Context for admin/services.html.j2 template."""

    services: list[dict[str, Any]] = Field(..., description="List of services with status")
    system_info: dict[str, Any] = Field(..., description="System information including uptime")
    deployment_type: str = Field(..., description="Current deployment type")


class SettingsPageContext(BaseTemplateContext):
    """Context for admin/settings.html.j2 template."""

    audio_devices: list[AudioDevice] = Field(..., description="Available audio devices")
    model_files: list[str] = Field(..., description="Available model files")
    metadata_model_files: list[str] = Field(..., description="Available metadata model files")


class AdvancedSettingsPageContext(BaseTemplateContext):
    """Context for admin/advanced_settings.html.j2 template."""

    config_yaml: str = Field(..., description="Raw YAML configuration content")


class UpdatePageContext(BaseTemplateContext):
    """Context for admin/update.html.j2 template.

    Note: Jinja2 templates can access Pydantic model attributes directly,
    so we pass the models themselves rather than dicts.
    """

    title: str = Field(..., description="Page title")
    update_status: UpdateStatusResponse = Field(..., description="Current update status")
    update_result: UpdateActionResponse | None = Field(
        default=None, description="Result of update operation"
    )
    sse_endpoint: str = Field(..., description="Server-Sent Events endpoint URL")
    git_remote: str = Field(..., description="Git remote name")
    git_branch: str = Field(..., description="Git branch name")
