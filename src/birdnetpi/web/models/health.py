"""Health check API response models."""

from typing import Any

from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """Response for basic health check endpoint."""

    status: str = Field(..., description="Health status (healthy/unhealthy)")
    timestamp: str = Field(..., description="ISO timestamp of health check")
    version: str = Field(..., description="Application version")
    service: str = Field(..., description="Service name")


class LivenessProbeResponse(BaseModel):
    """Response for Kubernetes liveness probe."""

    status: str = Field(..., description="Liveness status (alive)")


class ReadinessProbeResponse(BaseModel):
    """Response for Kubernetes readiness probe."""

    status: str = Field(..., description="Readiness status (ready/not_ready)")
    checks: dict[str, Any] = Field(..., description="Component readiness checks")
    timestamp: str = Field(..., description="ISO timestamp of readiness check")


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    status: str = Field(..., description="Component status (healthy/unhealthy)")
    type: str | None = Field(None, description="Component type (e.g., sqlite, redis)")
    error: str | None = Field(None, description="Error message if unhealthy")


class DetailedHealthResponse(BaseModel):
    """Response for detailed health check with all components."""

    status: str = Field(..., description="Overall health status (healthy/degraded)")
    timestamp: str = Field(..., description="ISO timestamp of health check")
    version: str = Field(..., description="Application version")
    service: str = Field(..., description="Service name")
    components: dict[str, ComponentHealth] = Field(
        ..., description="Health status of each component"
    )
