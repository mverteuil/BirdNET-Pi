"""Health check endpoints for monitoring service status."""

import logging
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.utils.cache.cache import Cache
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Health API"],
)


def get_version() -> str:
    """Get application version from pyproject.toml."""
    try:
        pyproject_path = Path("/opt/birdnetpi/pyproject.toml")
        if not pyproject_path.exists():
            # Fallback for development
            pyproject_path = Path(__file__).parent.parent.parent.parent.parent / "pyproject.toml"

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]
    except Exception as e:
        logger.warning(f"Could not read version from pyproject.toml: {e}")
        return "unknown"


@router.get("/")
async def health_check() -> dict[str, Any]:
    """Check basic health status of the service.

    Returns:
        Health status with timestamp and version.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": get_version(),
        "service": "birdnet-pi",
    }


@router.get("/live")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes-style liveness probe.

    Returns:
        Simple status indicating the service is alive.
    """
    return {"status": "alive"}


@router.get("/ready", status_code=200, response_model=None)
@inject
async def readiness_probe(
    db_service: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    response: Response,
) -> dict[str, Any]:
    """Check if service is ready to handle requests (Kubernetes readiness probe).

    Checks if the service is ready to handle requests by verifying
    database connectivity.

    Returns:
        Readiness status with component checks.
    """
    checks = {
        "database": False,
        "version": get_version(),
    }

    # Check database connectivity
    try:
        # Simple query to verify database is accessible
        async with db_service.get_async_db() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
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

    return {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/detailed", status_code=200, response_model=None)
@inject
async def detailed_health_check(
    db_service: Annotated[CoreDatabaseService, Depends(Provide[Container.core_database])],
    cache_service: Annotated[Cache, Depends(Provide[Container.cache_service])],
    response: Response,
) -> dict[str, Any]:
    """Provide detailed health check with component status.

    Returns:
        Comprehensive health status including all component checks.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": get_version(),
        "service": "birdnet-pi",
        "components": {},
    }

    # Check database
    try:
        async with db_service.get_async_db() as session:
            # Try a simple query
            await session.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "type": "sqlite",
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "degraded"

    # Check cache (Redis)
    try:
        # Test Redis connectivity with a simple ping
        cache_healthy = cache_service.ping()
        if cache_healthy:
            health_status["components"]["cache"] = {
                "status": "healthy",
                "type": "redis",
            }
        else:
            health_status["components"]["cache"] = {
                "status": "unhealthy",
                "error": "Redis ping failed",
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["cache"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "degraded"

    # Set appropriate status code for degraded state
    if health_status["status"] == "degraded":
        response.status_code = 503

    return health_status
