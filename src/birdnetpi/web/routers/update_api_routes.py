"""Update API routes for system update management."""

import logging
import subprocess
from typing import Annotated, Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request

from birdnetpi.config import BirdNETConfig
from birdnetpi.config.manager import ConfigManager
from birdnetpi.releases.region_pack_status import RegionPackStatusService
from birdnetpi.releases.registry_service import RegistryService
from birdnetpi.system.git_operations import GitOperationsService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_utils import SystemUtils
from birdnetpi.utils.auth import require_admin
from birdnetpi.utils.cache import Cache
from birdnetpi.web.core.container import Container
from birdnetpi.web.models.update import (
    GitBranchListResponse,
    GitConfigRequest,
    GitRemoteListResponse,
    GitRemoteModel,
    GitRemoteRequest,
    RegionPackDownloadStatusResponse,
    UpdateActionResponse,
    UpdateApplyRequest,
    UpdateCheckRequest,
    UpdateStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/update")


@router.post("/check")
@require_admin
@inject
async def check_for_updates(
    request: Request,
    update_request: UpdateCheckRequest,
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
            {"action": "check", "force": update_request.force},
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
        logger.error("Failed to check for updates: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/status")
@require_admin
@inject
async def get_update_status(
    request: Request,
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
        logger.error("Failed to get update status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/apply")
@require_admin
@inject
async def apply_update(
    request: Request,
    update_request: UpdateApplyRequest,
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
                "version": update_request.version,
                "dry_run": update_request.dry_run,
            },
            ttl=300,  # Request expires after 5 minutes
        )

        # Construct status message (not SQL)
        status_message = f"Update to version {update_request.version} has been queued"  # nosemgrep
        return UpdateActionResponse(
            success=True,
            message=status_message,
        )

    except Exception as e:
        logger.error("Failed to apply update: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/result")
@require_admin
@inject
async def get_update_result(
    request: Request,
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
        logger.error("Failed to get update result: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/cancel")
@require_admin
@inject
async def cancel_update(
    request: Request,
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
        logger.error("Failed to cancel update: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/git")
@require_admin
@inject
async def update_git_config(
    request: Request,
    git_config: GitConfigRequest,
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> UpdateActionResponse:
    """Update git configuration for system updates.

    Args:
        request: FastAPI request object (required by authentication decorator)
        git_config: Git configuration settings
        config: Current BirdNET configuration
        path_resolver: Path resolver for configuration paths

    Returns:
        Success/error response
    """
    try:
        # Update git settings on the config object
        config.updates.git_remote = git_config.git_remote
        config.updates.git_branch = git_config.git_branch

        # Save configuration using ConfigManager
        config_manager = ConfigManager(path_resolver)
        config_manager.save(config)

        logger.info(
            "Updated git configuration: remote=%s, branch=%s",
            git_config.git_remote,
            git_config.git_branch,
        )

        return UpdateActionResponse(
            success=True,
            message=f"Git configuration updated: {git_config.git_remote}/{git_config.git_branch}",
        )

    except ValueError as e:
        # Validation error from config model
        logger.warning("Invalid git configuration: %s", e)
        return UpdateActionResponse(
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error("Failed to update git configuration: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/git/remotes")
@require_admin
@inject
async def list_git_remotes(
    request: Request,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> GitRemoteListResponse:
    """List all configured git remotes.

    Returns:
        List of git remotes with names and URLs
    """
    try:
        # Only allow for SBC deployments
        deployment_type = SystemUtils.get_deployment_environment()
        if deployment_type == "docker":
            return GitRemoteListResponse(remotes=[])

        git_service = GitOperationsService(path_resolver)
        remotes = git_service.list_remotes()

        return GitRemoteListResponse(
            remotes=[GitRemoteModel(name=r.name, url=r.url) for r in remotes]
        )
    except subprocess.CalledProcessError as e:
        # Exit code 128 means not a git repository - return empty list
        if e.returncode == 128:
            logger.info("Not a git repository, returning empty remotes list")
            return GitRemoteListResponse(remotes=[])
        logger.error("Git command failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to list git remotes: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/git/remotes")
@require_admin
@inject
async def add_git_remote(
    request: Request,
    remote_request: GitRemoteRequest,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> UpdateActionResponse:
    """Add a new git remote.

    Args:
        request: FastAPI request object (required by authentication decorator)
        remote_request: Remote name and URL
        path_resolver: Path resolver for repository location

    Returns:
        Success/error response
    """
    try:
        # Only allow for SBC deployments
        deployment_type = SystemUtils.get_deployment_environment()
        if deployment_type == "docker":
            return UpdateActionResponse(
                success=False,
                error="Git remote management is not available for Docker deployments",
            )

        git_service = GitOperationsService(path_resolver)
        git_service.add_remote(remote_request.name, remote_request.url)

        return UpdateActionResponse(
            success=True,
            message=f"Git remote '{remote_request.name}' added successfully",
        )
    except subprocess.CalledProcessError as e:
        # Exit code 128 means not a git repository
        if e.returncode == 128:
            return UpdateActionResponse(
                success=False,
                error=(
                    "Installation directory is not a git repository. "
                    "Git-based updates are not available for this deployment."
                ),
            )
        logger.error("Git command failed: %s", e)
        return UpdateActionResponse(success=False, error=f"Git command failed: {e}")
    except ValueError as e:
        logger.warning("Invalid git remote request: %s", e)
        return UpdateActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error("Failed to add git remote: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/git/remotes/{remote_name}")
@require_admin
@inject
async def update_git_remote(
    request: Request,
    remote_name: str,
    remote_request: GitRemoteRequest,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> UpdateActionResponse:
    """Update an existing git remote URL.

    Args:
        request: FastAPI request object (required by authentication decorator)
        remote_name: Name of remote to update
        remote_request: New remote configuration
        path_resolver: Path resolver for repository location

    Returns:
        Success/error response
    """
    try:
        # Only allow for SBC deployments
        deployment_type = SystemUtils.get_deployment_environment()
        if deployment_type == "docker":
            return UpdateActionResponse(
                success=False,
                error="Git remote management is not available for Docker deployments",
            )

        git_service = GitOperationsService(path_resolver)

        # If name is changing, delete old and add new
        if remote_name != remote_request.name:
            # Can't rename origin
            if remote_name == "origin":
                return UpdateActionResponse(
                    success=False,
                    error="Cannot rename 'origin' remote. Edit URL only.",
                )
            git_service.delete_remote(remote_name)
            git_service.add_remote(remote_request.name, remote_request.url)
        else:
            # Just update URL
            git_service.update_remote(remote_request.name, remote_request.url)

        return UpdateActionResponse(
            success=True,
            message=f"Git remote '{remote_request.name}' updated successfully",
        )
    except ValueError as e:
        logger.warning("Invalid git remote update: %s", e)
        return UpdateActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error("Failed to update git remote: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/git/remotes/{remote_name}")
@require_admin
@inject
async def delete_git_remote(
    request: Request,
    remote_name: str,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> UpdateActionResponse:
    """Delete a git remote.

    Args:
        request: FastAPI request object (required by authentication decorator)
        remote_name: Name of remote to delete
        path_resolver: Path resolver for repository location

    Returns:
        Success/error response

    Note:
        The 'origin' remote cannot be deleted for safety.
    """
    try:
        # Only allow for SBC deployments
        deployment_type = SystemUtils.get_deployment_environment()
        if deployment_type == "docker":
            return UpdateActionResponse(
                success=False,
                error="Git remote management is not available for Docker deployments",
            )

        git_service = GitOperationsService(path_resolver)
        git_service.delete_remote(remote_name)

        return UpdateActionResponse(
            success=True,
            message=f"Git remote '{remote_name}' deleted successfully",
        )
    except ValueError as e:
        logger.warning("Cannot delete git remote: %s", e)
        return UpdateActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error("Failed to delete git remote: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/git/branches/{remote_name}")
@require_admin
@inject
async def list_git_branches(
    request: Request,
    remote_name: str,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
) -> GitBranchListResponse:
    """List branches and tags for a git remote.

    Args:
        request: FastAPI request object (required by authentication decorator)
        remote_name: Name of remote to query
        path_resolver: Path resolver for repository location

    Returns:
        Lists of tags and branches
    """
    try:
        # Only allow for SBC deployments
        deployment_type = SystemUtils.get_deployment_environment()
        if deployment_type == "docker":
            return GitBranchListResponse(tags=[], branches=[])

        git_service = GitOperationsService(path_resolver)
        tags = git_service.list_tags(remote_name)
        branches = git_service.list_branches(remote_name)

        return GitBranchListResponse(tags=tags, branches=branches)
    except subprocess.CalledProcessError as e:
        # Exit code 128 means not a git repository - return empty lists
        if e.returncode == 128:
            logger.info("Not a git repository, returning empty branches/tags list")
            return GitBranchListResponse(tags=[], branches=[])
        logger.error("Git command failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to list branches for remote '%s': %s", remote_name, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/region-pack/status")
@require_admin
@inject
async def get_region_pack_status(
    request: Request,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> dict[str, Any]:
    """Get region pack status.

    Returns:
        Status information about configured region pack
    """
    service = RegionPackStatusService(path_resolver, config)
    return service.check_status()


@router.get("/region-pack/available")
@require_admin
@inject
async def list_available_region_packs(
    request: Request,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
) -> dict[str, Any]:
    """List available region pack files.

    Returns:
        List of available region pack names
    """
    service = RegionPackStatusService(path_resolver, config)
    packs = service.list_available_packs()
    return {
        "packs": [p.name for p in packs],
        "count": len(packs),
    }


@router.post("/region-pack/download")
@require_admin
@inject
async def download_region_pack(
    request: Request,
    path_resolver: Annotated[PathResolver, Depends(Provide[Container.path_resolver])],
    config: Annotated[BirdNETConfig, Depends(Provide[Container.config])],
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> UpdateActionResponse:
    """Download appropriate region pack based on configured coordinates.

    Uses the region pack registry to find the appropriate pack for the
    configured latitude/longitude, then queues a download request.

    Returns:
        Success/error response with download information
    """
    try:
        # Get coordinates from config
        lat = config.latitude
        lon = config.longitude

        if lat == 0.0 and lon == 0.0:
            return UpdateActionResponse(
                success=False,
                error=(
                    "Location coordinates not configured. "
                    "Please set latitude and longitude in settings."
                ),
            )

        # Find appropriate region pack
        registry_service = RegistryService(path_resolver)
        region_pack = registry_service.find_pack_for_coordinates(lat, lon)

        if not region_pack:
            return UpdateActionResponse(
                success=False,
                error=f"No region pack found for coordinates ({lat}, {lon}). "
                "This location may not be covered by available packs.",
            )

        if not region_pack.download_url:
            return UpdateActionResponse(
                success=False,
                error=f"Region pack '{region_pack.region_id}' found but has no download URL.",
            )

        # Queue download request for update daemon
        cache.set(
            "region_pack:download_request",
            {
                "region_id": region_pack.region_id,
                "download_url": region_pack.download_url,
                "size_mb": region_pack.total_size_mb,
            },
            ttl=300,  # Request expires after 5 minutes
        )

        return UpdateActionResponse(
            success=True,
            message=(
                f"Download queued for region pack '{region_pack.region_id}' "
                f"({region_pack.total_size_mb:.1f} MB)"
            ),
        )

    except Exception as e:
        logger.error("Failed to download region pack: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/region-pack/download-status", response_model=RegionPackDownloadStatusResponse)
@require_admin
@inject
async def get_region_pack_download_status(
    request: Request,
    cache: Annotated[Cache, Depends(Provide[Container.cache_service])],
) -> RegionPackDownloadStatusResponse:
    """Get region pack download progress.

    Returns:
        Download status including progress percentage.
        Status can be: idle, downloading, complete, or error.
    """
    status = cache.get("region_pack:download_status")
    if not status:
        return RegionPackDownloadStatusResponse(status="idle")
    return RegionPackDownloadStatusResponse(**status)
