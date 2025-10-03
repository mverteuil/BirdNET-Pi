"""Health check endpoints for monitoring service status."""

import logging
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.system import PathResolver
from birdnetpi.utils.cache.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.health import (
    ComponentHealth,
    DetailedHealthResponse,
    HealthCheckResponse,
    LivenessProbeResponse,
    ReadinessProbeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health")


def get_version(path_resolver: PathResolver) -> str:
    """Get application version from pyproject.toml."""
    try:
        pyproject_path = Path("/opt/birdnetpi/pyproject.toml")
        if not pyproject_path.exists():
            # Fallback for development
            pyproject_path = path_resolver.get_repo_path() / "pyproject.toml"

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]
    except Exception as e:
        logger.warning("Could not read version from pyproject.toml: %s", e)
        return "unknown"


@router.get("/", response_model=HealthCheckResponse)
@inject
async def health_check(
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> HealthCheckResponse:
    """Check basic health status of the service.

    Returns:
        Health status with timestamp and version.
    """
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version=get_version(path_resolver),
        service="birdnet-pi",
    )


@router.get("/live", response_model=LivenessProbeResponse)
async def liveness_probe() -> LivenessProbeResponse:
    """Kubernetes-style liveness probe.

    Returns:
        Simple status indicating the service is alive.
    """
    return LivenessProbeResponse(status="alive")


@router.get("/ready", status_code=200, response_model=ReadinessProbeResponse)
@inject
async def readiness_probe(
    db_service: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    response: Response,
) -> ReadinessProbeResponse:
    """Check if service is ready to handle requests (Kubernetes readiness probe).

    Checks if the service is ready to handle requests by verifying
    database connectivity.

    Returns:
        Readiness status with component checks.
    """
    checks = {
        "database": False,
        "version": get_version(path_resolver),
    }

    # Check database connectivity
    try:
        # Simple query to verify database is accessible
        async with db_service.get_async_db() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        checks["database"] = False

    # Overall status
    is_ready = all(
        [
            checks["database"],
        ]
    )

    # Set appropriate status code
    if not is_ready:
        response.status_code = 503

    return ReadinessProbeResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.get("/detailed", status_code=200, response_model=DetailedHealthResponse)
@inject
async def detailed_health_check(
    db_service: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    cache_service: Annotated[Cache, Depends(Provide[Container.cache_service])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    response: Response,
) -> DetailedHealthResponse:
    """Provide detailed health check with component status.

    Returns:
        Comprehensive health status including all component checks.
    """
    components: dict[str, ComponentHealth] = {}
    overall_status = "healthy"

    # Check database
    try:
        async with db_service.get_async_db() as session:
            # Try a simple query
            await session.execute(text("SELECT 1"))
        components["database"] = ComponentHealth(
            status="healthy",
            type="sqlite",
            error=None,
        )
    except Exception as e:
        components["database"] = ComponentHealth(
            status="unhealthy",
            type=None,
            error=str(e),
        )
        overall_status = "degraded"

    # Check cache (Redis)
    try:
        # Test Redis connectivity with a simple ping
        cache_healthy = cache_service.ping()
        if cache_healthy:
            components["cache"] = ComponentHealth(
                status="healthy",
                type="redis",
                error=None,
            )
        else:
            components["cache"] = ComponentHealth(
                status="unhealthy",
                type=None,
                error="Redis ping failed",
            )
            overall_status = "degraded"
    except Exception as e:
        components["cache"] = ComponentHealth(
            status="unhealthy",
            type=None,
            error=str(e),
        )
        overall_status = "degraded"

    # Set appropriate status code for degraded state
    if overall_status == "degraded":
        response.status_code = 503

    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version=get_version(path_resolver),
        service="birdnet-pi",
        components=components,
    )
