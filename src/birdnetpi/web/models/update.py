"""Update-related API contract models."""

from pydantic import BaseModel


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
