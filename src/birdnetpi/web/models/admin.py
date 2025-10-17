"""Admin API contract models."""

from pydantic import BaseModel, Field

# ==================== Request Models ====================


class YAMLConfigRequest(BaseModel):
    """Request model for YAML configuration operations."""

    yaml_content: str


# ==================== Response Models ====================


class ValidationResponse(BaseModel):
    """Response for configuration validation."""

    valid: bool = Field(..., description="Whether the configuration is valid")
    message: str | None = Field(None, description="Success message if valid")
    error: str | None = Field(None, description="Error message if invalid")


class SaveConfigResponse(BaseModel):
    """Response for configuration save operation."""

    success: bool = Field(..., description="Whether the save was successful")
    message: str | None = Field(None, description="Success message")
    error: str | None = Field(None, description="Error message if failed")


class EBirdCleanupPreviewRequest(BaseModel):
    """Request to preview eBird cleanup operation."""

    strictness: str = Field(..., description="Strictness level: vagrant, rare, uncommon, common")
    region_pack: str = Field(..., description="Name of region pack (e.g., 'na-east-coast-2025.08')")
    h3_resolution: int = Field(5, description="H3 resolution for lookups (default: 5)")
    limit: int | None = Field(None, description="Optional limit on detections to check")


class EBirdCleanupRequest(BaseModel):
    """Request to perform eBird cleanup operation."""

    strictness: str = Field(..., description="Strictness level: vagrant, rare, uncommon, common")
    region_pack: str = Field(..., description="Name of region pack (e.g., 'na-east-coast-2025.08')")
    h3_resolution: int = Field(5, description="H3 resolution for lookups (default: 5)")
    limit: int | None = Field(None, description="Optional limit on detections to process")
    delete_audio: bool = Field(True, description="Whether to delete associated audio files")
    confirm: bool = Field(False, description="Confirmation required for cleanup")


class EBirdCleanupResponse(BaseModel):
    """Response from eBird cleanup operation."""

    success: bool
    message: str
    stats: dict | None = None  # CleanupStats.to_dict() result
