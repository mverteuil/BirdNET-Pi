"""i18n API response models."""

from typing import Any

from pydantic import BaseModel, Field


class TranslationsResponse(BaseModel):
    """Response for JavaScript translations endpoint."""

    language: str = Field(..., description="Language code")
    translations: dict[str, str] = Field(
        ..., description="Translation key-value pairs for JavaScript"
    )


class LanguageCatalogResponse(BaseModel):
    """Response for complete language catalog endpoint."""

    language: str = Field(..., description="Language code")
    catalog: dict[str, Any] = Field(..., description="Complete translation catalog")
