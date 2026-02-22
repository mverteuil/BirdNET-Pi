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
    deployment_type: str | None = None  # docker, sbc, or unknown


class UpdateActionResponse(BaseModel):
    """Response model for update actions."""

    success: bool
    message: str | None = None
    error: str | None = None


class GitConfigRequest(BaseModel):
    """Request model for updating git configuration."""

    git_remote: str
    git_branch: str


class GitRemoteModel(BaseModel):
    """Model for a git remote."""

    name: str
    url: str


class GitRemoteListResponse(BaseModel):
    """Response model for listing git remotes."""

    remotes: list[GitRemoteModel]


class GitRemoteRequest(BaseModel):
    """Request model for adding/updating a git remote."""

    name: str
    url: str


class GitBranchListResponse(BaseModel):
    """Response model for listing branches and tags."""

    tags: list[str]
    branches: list[str]


class RegionPackDownloadStatusResponse(BaseModel):
    """Response model for region pack download status.

    Status values:
    - idle: No download in progress
    - downloading: Download is in progress
    - complete: Download finished successfully
    - error: Download failed
    """

    status: str  # idle, downloading, complete, error
    region_id: str | None = None
    progress: int | None = None  # 0-100 percentage
    downloaded_mb: float | None = None
    total_mb: float | None = None
    error: str | None = None
