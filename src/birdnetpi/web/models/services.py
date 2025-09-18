"""Pydantic models for service status and system information."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class ServiceConfig:
    """Configuration for a system service."""

    name: str
    description: str
    critical: bool = False
    optional: bool = False


class ServiceStatus(BaseModel):
    """Model for a single service's status information."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "fastapi",
                "description": "Web interface and API",
                "status": "active",
                "pid": 1234,
                "uptime_seconds": 3600.5,
                "start_time": "2024-01-15T10:30:00",
                "critical": True,
                "optional": False,
            }
        }
    )

    name: str = Field(..., description="Service name as known to the service manager")
    description: str = Field(..., description="Human-readable service description")
    status: str = Field(
        ...,
        description="Service status: active, inactive, starting, failed, unknown, error",
        pattern="^(active|inactive|starting|failed|unknown|error)$",
    )
    pid: int | None = Field(None, description="Process ID if service is running")
    uptime_seconds: float | None = Field(None, description="Service uptime in seconds if running")
    uptime_formatted: str | None = Field(None, description="Human-readable uptime string")
    start_time: str | None = Field(None, description="ISO formatted start time if available")
    sub_state: str | None = Field(
        None, description="Additional state information (e.g., 'running', 'dead')"
    )
    critical: bool = Field(
        default=False, description="Whether this is a critical service requiring warnings"
    )
    optional: bool = Field(
        default=False, description="Whether this service may not be available in all deployments"
    )


class ServiceActionRequest(BaseModel):
    """Model for service action requests."""

    model_config = ConfigDict(json_schema_extra={"example": {"confirm": True}})

    confirm: bool = Field(
        default=False, description="Confirmation flag for critical service actions"
    )


class ServiceActionResponse(BaseModel):
    """Model for service action responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Service 'fastapi' restarted successfully",
                "service": "fastapi",
                "action": "restart",
            }
        }
    )

    success: bool = Field(..., description="Whether the action succeeded")
    message: str = Field(..., description="Human-readable result message")
    service: str = Field(..., description="Service name")
    action: str = Field(..., description="Action that was performed")
    error: str | None = Field(default=None, description="Error message if action failed")


class SystemInfo(BaseModel):
    """Model for system/container information."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uptime_seconds": 86400.5,
                "uptime_formatted": "1 day, 0:00:00",
                "reboot_available": True,
                "deployment_type": "docker",
                "hostname": "birdnetpi",
            }
        }
    )

    uptime_seconds: float = Field(..., description="System/container uptime in seconds")
    uptime_formatted: str = Field(..., description="Human-readable uptime string")
    reboot_available: bool = Field(..., description="Whether system/container reboot is available")
    deployment_type: str = Field(..., description="Deployment type: docker, sbc, or unknown")
    hostname: str | None = Field(None, description="System hostname if available")


class SystemRebootRequest(BaseModel):
    """Model for system reboot requests."""

    model_config = ConfigDict(json_schema_extra={"example": {"confirm": True, "force": False}})

    confirm: bool = Field(
        default=False, description="Confirmation required to prevent accidental reboots"
    )
    force: bool = Field(
        default=False, description="Force reboot even if services are not responding"
    )


class SystemRebootResponse(BaseModel):
    """Model for system reboot responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "System reboot initiated. The system will restart in a few seconds.",
                "reboot_initiated": True,
            }
        }
    )

    success: bool = Field(..., description="Whether the reboot was initiated")
    message: str = Field(..., description="Human-readable result message")
    reboot_initiated: bool = Field(..., description="Whether reboot actually started")
    error: str | None = Field(default=None, description="Error message if reboot failed")


class ConfigReloadResponse(BaseModel):
    """Model for configuration reload responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Configuration reloaded successfully",
                "changes_detected": True,
                "services_affected": ["audio_capture", "audio_analysis"],
            }
        }
    )

    success: bool = Field(..., description="Whether the configuration reload succeeded")
    message: str = Field(..., description="Human-readable result message")
    changes_detected: bool = Field(
        default=False, description="Whether configuration changes were detected"
    )
    services_affected: list[str] = Field(
        default_factory=list, description="Services affected by configuration changes"
    )
    error: str | None = Field(default=None, description="Error message if reload failed")


class ServicesStatusResponse(BaseModel):
    """Model for the complete services status response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "services": [
                    {
                        "name": "fastapi",
                        "description": "Web interface and API",
                        "status": "active",
                        "pid": 1234,
                        "uptime_seconds": 3600.5,
                        "critical": True,
                    },
                    {
                        "name": "audio_capture",
                        "description": "Audio recording service",
                        "status": "active",
                        "pid": 1235,
                        "uptime_seconds": 3598.2,
                    },
                ],
                "system": {
                    "uptime_seconds": 86400.5,
                    "uptime_formatted": "1 day, 0:00:00",
                    "reboot_available": True,
                    "deployment_type": "docker",
                },
            }
        }
    )

    services: list[ServiceStatus] = Field(..., description="List of all services and their status")
    system: SystemInfo = Field(..., description="System/container information")


def format_uptime(seconds: float | None) -> str:
    """Format uptime seconds into human-readable string.

    Args:
        seconds: Uptime in seconds

    Returns:
        Formatted string like "2 days, 3:45:30" or "Unknown"
    """
    if seconds is None or seconds < 0:
        return "Unknown"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if days > 0:
        return f"{days} day{'s' if days != 1 else ''}, {hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{hours}:{minutes:02d}:{secs:02d}"
