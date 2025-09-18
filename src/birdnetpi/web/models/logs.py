"""Pydantic models for log viewing functionality."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

if TYPE_CHECKING:
    pass


class LogEntry(BaseModel):
    """Model for a single log entry."""

    model_config = ConfigDict(
        json_encoders=None,  # Not needed with field_serializer
    )

    timestamp: datetime = Field(..., description="When the log entry was created")
    service: str = Field(..., description="Name of the service that generated the log")
    level: str = Field(
        default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    message: str = Field(..., description="The log message content")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional structured data")
    raw: bool = Field(default=False, description="Whether this was parsed from unstructured text")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime | None, _info: Any) -> str | None:  # noqa: ANN401
        """Serialize timestamp to ISO format."""
        return timestamp.isoformat() if timestamp else None


class LogFilter(BaseModel):
    """Model for log filtering parameters."""

    services: list[str] = Field(default_factory=list, description="List of services to include")
    level: str | None = Field(None, description="Minimum log level (hierarchical)")
    start_time: datetime | None = Field(None, description="Start of time range")
    end_time: datetime | None = Field(None, description="End of time range")
    keyword: str | None = Field(None, description="Keyword to search in messages")
    limit: int = Field(default=1000, ge=1, le=10000, description="Maximum entries to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class LogStreamRequest(BaseModel):
    """Model for SSE streaming request parameters."""

    services: list[str] = Field(default_factory=list, description="Services to stream logs from")
    level: str | None = Field(None, description="Minimum log level to stream")
    keyword: str | None = Field(None, description="Keyword filter for streaming")


class LogLevelInfo(BaseModel):
    """Information about a log level for UI display."""

    name: str = Field(..., description="Level name (e.g., 'ERROR')")
    value: int = Field(..., description="Numeric value for hierarchy")
    color: str = Field(..., description="Hex color code for display")
    aria_label: str = Field(..., description="Accessibility label")


# Predefined log levels with colorblind-safe colors
LOG_LEVELS = [
    LogLevelInfo(
        name="DEBUG",
        value=10,
        color="#6c757d",  # Gray
        aria_label="Debug level",
    ),
    LogLevelInfo(
        name="INFO",
        value=20,
        color="#0066cc",  # Blue
        aria_label="Information level",
    ),
    LogLevelInfo(
        name="WARNING",
        value=30,
        color="#ff9900",  # Orange
        aria_label="Warning level",
    ),
    LogLevelInfo(
        name="ERROR",
        value=40,
        color="#9933ff",  # Purple
        aria_label="Error level",
    ),
    LogLevelInfo(
        name="CRITICAL",
        value=50,
        color="#330066",  # Dark purple
        aria_label="Critical level",
    ),
]


def get_log_level_info(level: str) -> LogLevelInfo:
    """Get display information for a log level.

    Args:
        level: Log level name

    Returns:
        LogLevelInfo with display properties
    """
    for info in LOG_LEVELS:
        if info.name == level.upper():
            return info
    # Default to INFO if unknown
    return LOG_LEVELS[1]
