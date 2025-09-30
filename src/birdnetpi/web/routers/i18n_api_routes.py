"""i18n API routes for JavaScript translations."""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.web.core.container import Container

router = APIRouter(prefix="/api/i18n")


@router.get("/translations")
@inject
async def get_translations_json(
    request: Request,
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
    lang: str | None = None,
) -> JSONResponse:
    """Get translations for JavaScript as JSON.

    Args:
        request: FastAPI request object
        lang: Optional language code override
        translation_manager: Translation manager from DI container

    Returns:
        JSON object with all translated strings for the current language
    """
    # Get the translation for the specified language or from request headers
    if not lang:
        # Parse Accept-Language header if no lang specified
        accept_language = request.headers.get("Accept-Language", "en")
        lang = accept_language.split(",")[0].split("-")[0]

    translation = translation_manager.get_translation(lang)

    # Define all translatable strings used in JavaScript
    # These should match the keys used in JavaScript getI18n() calls
    js_translations = {
        # Audio/connection messages
        "audio-not-available": translation.gettext("Audio not available"),
        "connect-audio": translation.gettext("Connect Audio"),
        "disconnect-audio": translation.gettext("Disconnect Audio"),
        # Time periods
        "today": translation.gettext("Today"),
        "last-7-days": translation.gettext("Last 7 days"),
        "last-30-days": translation.gettext("Last 30 days"),
        "all-time": translation.gettext("All time"),
        # Filters and selections
        "all-families": translation.gettext("All families"),
        "all-genera": translation.gettext("All genera"),
        "all-species": translation.gettext("All species"),
        "select-family": translation.gettext("Select family first"),
        "select-genus": translation.gettext("Select genus first"),
        # Loading states
        "loading": translation.gettext("Loading..."),
        "checking": translation.gettext("Checking..."),
        "error": translation.gettext("Error"),
        "error-genera": translation.gettext("Error loading genera"),
        "error-species": translation.gettext("Error loading species"),
        # Taxonomy labels
        "family": translation.gettext("Family"),
        "genus": translation.gettext("Genus"),
        "species": translation.gettext("Species"),
        # Actions
        "play-recording": translation.gettext("Play recording"),
        "filter-by-genus": translation.gettext("Filter by genus"),
        "filter-by-species": translation.gettext("Filter by species"),
        "filter-by-family": translation.gettext("Filter by family"),
        # Statistics
        "recordings": translation.gettext("recordings"),
        "species-count": translation.gettext("species"),
        "detections": translation.gettext("detections"),
        "average-confidence": translation.gettext("Average confidence"),
        "date-range": translation.gettext("Date range"),
        # Update messages
        "check-for-updates": translation.gettext("🔄 Check for Updates"),
        "update-available": translation.gettext("Update Available"),
        "up-to-date": translation.gettext("Up to Date"),
        "starting-test-update": translation.gettext("Starting test update..."),
        "starting-update": translation.gettext("Starting update..."),
        "update-cancelled": translation.gettext("Update cancelled"),
        # Configuration messages
        "discard-changes": translation.gettext("Discard all unsaved changes?"),
        "config-saved": translation.gettext(
            "Configuration saved. Restart BirdNET-Pi services to apply changes."
        ),
        "save-failed": translation.gettext("Failed to save: %(error)s"),
        "saved-status": translation.gettext("Saved"),
        "save-failed-status": translation.gettext("Save failed"),
        "reset-success": translation.gettext("Reset to saved configuration"),
        "validation-passed": translation.gettext("Configuration is valid"),
        "validation-error": translation.gettext("Validation error: %(error)s"),
        "modified-status": translation.gettext("Modified"),
        "ready-status": translation.gettext("Ready"),
        "modified-valid-status": translation.gettext("Modified (valid)"),
        # Error messages
        "invalid-remote-format": translation.gettext("Invalid remote name format"),
        "invalid-branch-format": translation.gettext("Invalid branch name format"),
        "failed-to-save-config": translation.gettext("Failed to save configuration"),
        "failed-to-check-updates": translation.gettext("Failed to check for updates"),
        "failed-to-apply-update": translation.gettext("Failed to apply update"),
        "failed-to-cancel-update": translation.gettext("Failed to cancel update"),
        "failed-to-save-git-config": translation.gettext("Failed to save git configuration"),
    }

    # Use the language we determined earlier
    return JSONResponse(content={"language": lang, "translations": js_translations})


@router.get("/catalog/{lang}")
@inject
async def get_language_catalog(
    lang: str,
    translation_manager: Annotated[
        TranslationManager, Depends(Provide[Container.translation_manager])
    ],
) -> JSONResponse:
    """Get the full translation catalog for a specific language.

    This can be used for loading complete translation sets in single-page applications.

    Args:
        lang: Language code to get catalog for
        translation_manager: Translation manager from DI container

    Returns:
        JSON object with complete translation catalog
    """
    translation = translation_manager.get_translation(lang)

    # Get the catalog from the translation object
    catalog = {}
    if hasattr(translation, "_catalog"):
        # Extract messages from the catalog
        # Use getattr to avoid type checking issues with private attribute
        translation_catalog = getattr(translation, "_catalog", None)
        if translation_catalog:
            for msg in translation_catalog:
                if msg.id and msg.string:
                    catalog[msg.id] = msg.string

    return JSONResponse(content={"language": lang, "catalog": catalog})
