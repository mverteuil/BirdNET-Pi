"""Admin API contract models."""

from pydantic import BaseModel


class YAMLConfigRequest(BaseModel):
    """Request model for YAML configuration operations."""

    yaml_content: str
