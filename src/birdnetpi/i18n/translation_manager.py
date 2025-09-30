"""Translation service for BirdNET-Pi internationalization.

Uses Python's gettext with Babel for extraction/compilation.
"""

from gettext import GNUTranslations, NullTranslations, ngettext, translation
from typing import TYPE_CHECKING

from fastapi import Request

from birdnetpi.system.path_resolver import PathResolver

if TYPE_CHECKING:
    from starlette.templating import Jinja2Templates


class TranslationManager:
    """Manages translations for the application."""

    def __init__(self, path_resolver: PathResolver):
        self.path_resolver = path_resolver
        # Locale files (.po/.mo) are source files, stored in app directory
        self.locales_dir = path_resolver.get_locales_dir()
        self.translations: dict[str, GNUTranslations | NullTranslations] = {}
        self.default_language = "en"

    def get_translation(self, language: str) -> GNUTranslations | NullTranslations:
        """Get translation object for a specific language."""
        if language not in self.translations:
            try:
                self.translations[language] = translation(
                    "messages", localedir=self.locales_dir, languages=[language], fallback=True
                )
            except FileNotFoundError:
                # Fallback to default language
                self.translations[language] = translation(
                    "messages",
                    localedir=self.locales_dir,
                    languages=[self.default_language],
                    fallback=True,
                )
        return self.translations[language]

    def install_for_request(self, request: Request) -> GNUTranslations | NullTranslations:
        """Install translation for current request.

        Based on Accept-Language header or lang query param.
        """
        # Check query parameter first (for testing)
        language = request.query_params.get("lang")

        if not language:
            # Parse Accept-Language header
            accept_language = request.headers.get("Accept-Language", self.default_language)
            language = accept_language.split(",")[0].split("-")[0]  # Extract primary language code

        # Get translation and install it
        translation = self.get_translation(language)
        translation.install()  # Makes _() available globally

        return translation


# FastAPI dependency
def get_translation(request: Request) -> GNUTranslations:
    """FastAPI dependency to get translation for current request."""
    translation_manager = request.app.state.translation_manager
    return translation_manager.install_for_request(request)


# Jinja2 integration
def setup_jinja2_i18n(templates: "Jinja2Templates") -> None:
    """Configure Jinja2 templates with i18n support."""

    def get_text(message: str, **kwargs: object) -> str:
        """Template function for translations with parameter interpolation.

        Supports both simple messages and messages with parameters:
        - _('Simple message')
        - _('Hello %(name)s', name='World')
        - _('%(count)d items', count=5)
        """
        import builtins

        # Get the current _ function from builtins (where install() puts it)
        current_gettext = getattr(builtins, "_", lambda x: x)
        translated = current_gettext(message)

        # If kwargs provided, do parameter substitution
        if kwargs:
            try:
                # Use % formatting for consistency with gettext conventions
                translated = translated % kwargs
            except (TypeError, KeyError, ValueError):
                # If substitution fails, return the translated string as-is
                pass

        return translated

    templates.env.globals["_"] = get_text
    templates.env.globals["gettext"] = get_text

    # Add ngettext for pluralization
    templates.env.globals["ngettext"] = ngettext
