"""Language detection utilities for i18n support."""

from fastapi import Request

from birdnetpi.config.models import BirdNETConfig


def get_user_language(request: Request, config: BirdNETConfig) -> str:
    """Get user's preferred language with precedence order.

    Precedence (highest to lowest):
    1. Query parameter (?lang=fr)
    2. Accept-Language header
    3. Config file default language

    Args:
        request: FastAPI request object
        config: Application configuration

    Returns:
        Two-letter language code (e.g., 'en', 'fr', 'de')
    """
    # 1. Check query parameter first (highest priority)
    lang_param = request.query_params.get("lang")
    if lang_param:
        return lang_param.split("-")[0].lower()

    # 2. Check Accept-Language header
    accept_lang = request.headers.get("Accept-Language")
    if accept_lang:
        # Parse Accept-Language: "en-US,en;q=0.9,fr;q=0.8"
        # Take first language and extract base code
        return accept_lang.split(",")[0].split("-")[0].lower()

    # 3. Fall back to config default language
    return getattr(config, "default_language", "en")
