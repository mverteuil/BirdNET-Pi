"""Update API routes for system update management."""

import logging
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from birdnetpi.config import BirdNETConfig
from birdnetpi.config.manager import ConfigManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter()


class UpdateCheckRequest(BaseModel):
    """Request model for checking for updates."""

    force: bool = False  # Force check even if recently checked


class UpdateApplyRequest(BaseModel):
    """Request model for applying an update."""

    version: str  # Version to update to
    dry_run: bool = False  # Test update without applying


class UpdateStatusResponse(BaseModel):
    """Response model for update status."""

    available: bool
    current_version: str | None = None
    latest_version: str | None = None
    release_notes: str | None = None
    release_url: str | None = None
    can_auto_update: bool = False
    error: str | None = None


class UpdateActionResponse(BaseModel):
    """Response model for update actions."""

    success: bool
    message: str | None = None
    error: str | None = None


class GitConfigRequest(BaseModel):
    """Request model for updating git configuration."""

    git_remote: str
    git_branch: str


@router.post("/check")
@inject
async def check_for_updates(
    request: UpdateCheckRequest,
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> UpdateStatusResponse:
    """Check for available updates.

    This endpoint queues a check request for the update daemon
    and returns the current update status.
    """
    try:
        # Queue the check request for the update daemon
        cache.set(
            "update:request",
            {"action": "check", "force": request.force},
            ttl=60,  # Request expires after 1 minute
        )

        # Try to get cached status immediately (daemon may have recent check)
        status = cache.get("update:status")
        if status:
            return UpdateStatusResponse(**status)

        # No cached status, return default
        return UpdateStatusResponse(
            available=False,
            error="Update check in progress, please refresh in a moment",
        )

    except Exception as e:
        logger.error(f"Failed to check for updates: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
@inject
async def get_update_status(
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> UpdateStatusResponse:
    """Get current update status from cache.

    Returns the last known update status without triggering a new check.
    """
    try:
        status = cache.get("update:status")
        if status:
            return UpdateStatusResponse(**status)

        return UpdateStatusResponse(
            available=False,
            error="No update status available. Please check for updates.",
        )

    except Exception as e:
        logger.error(f"Failed to get update status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/apply")
@inject
async def apply_update(
    request: UpdateApplyRequest,
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> UpdateActionResponse:
    """Apply a system update.

    This endpoint queues an update request for the update daemon.
    The actual update is performed asynchronously.

    Use the /api/update/stream SSE endpoint to monitor progress.
    """
    try:
        # Check if an update is already in progress
        existing_request = cache.get("update:request")
        if existing_request:
            return UpdateActionResponse(
                success=False,
                error="An update operation is already in progress",
            )

        # Queue the update request for the daemon
        cache.set(
            "update:request",
            {
                "action": "apply",
                "version": request.version,
                "dry_run": request.dry_run,
            },
            ttl=300,  # Request expires after 5 minutes
        )

        # Construct status message (not SQL)
        status_message = f"Update to version {request.version} has been queued"  # nosemgrep
        return UpdateActionResponse(
            success=True,
            message=status_message,
        )

    except Exception as e:
        logger.error(f"Failed to apply update: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/result")
@inject
async def get_update_result(
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> dict[str, Any]:
    """Get the result of the last update operation.

    Returns details about the last update attempt, including success/failure
    and any error messages.
    """
    try:
        result = cache.get("update:result")
        if result:
            return result

        return {
            "success": False,
            "error": "No update result available",
        }

    except Exception as e:
        logger.error(f"Failed to get update result: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/cancel")
@inject
async def cancel_update(
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> UpdateActionResponse:
    """Cancel a pending update request.

    This only cancels queued requests. Updates already in progress
    cannot be cancelled for safety reasons.
    """
    try:
        request = cache.get("update:request")
        if not request:
            return UpdateActionResponse(
                success=False,
                error="No update request to cancel",
            )

        # Only allow cancelling if not yet started
        if request.get("action") == "apply":
            # Check if update is actually in progress
            # (Would need additional state tracking in daemon)
            cache.delete("update:request")
            return UpdateActionResponse(
                success=True,
                message="Update request cancelled",
            )

        cache.delete("update:request")
        return UpdateActionResponse(
            success=True,
            message="Check request cancelled",
        )

    except Exception as e:
        logger.error(f"Failed to cancel update: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/git")
@inject
async def update_git_config(
    request: GitConfigRequest,
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> UpdateActionResponse:
    """Update git configuration for system updates.

    Args:
        request: Git configuration settings
        config: Current BirdNET configuration
        path_resolver: Path resolver for configuration paths

    Returns:
        Success/error response
    """
    try:
        # Update git settings on the config object
        config.updates.git_remote = request.git_remote
        config.updates.git_branch = request.git_branch

        # Save configuration using ConfigManager
        config_manager = ConfigManager(path_resolver)
        config_manager.save(config)

        logger.info(
            f"Updated git configuration: remote={request.git_remote}, branch={request.git_branch}"
        )

        return UpdateActionResponse(
            success=True,
            message=f"Git configuration updated: {request.git_remote}/{request.git_branch}",
        )

    except ValueError as e:
        # Validation error from config model
        logger.warning(f"Invalid git configuration: {e}")
        return UpdateActionResponse(
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to update git configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
