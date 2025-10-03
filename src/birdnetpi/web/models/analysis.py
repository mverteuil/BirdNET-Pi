"""Analysis API response models."""

from typing import Any

from pydantic import BaseModel, Field


class AnalysisDataResponse(BaseModel):
    """Response for analysis data endpoint."""

    analyses: dict[str, Any] = Field(
        ..., description="Analysis results (diversity, temporal patterns, weather, etc.)"
    )
    summary: dict[str, Any] = Field(..., description="Summary statistics for the period")
    generated_at: str = Field(..., description="Timestamp when analysis was generated")
