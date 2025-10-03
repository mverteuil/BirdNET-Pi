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
