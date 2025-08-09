"""Tests for TranslationManager."""

import gettext
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from starlette.templating import Jinja2Templates

from birdnetpi.managers.translation_manager import (
    TranslationManager,
    get_translation,
    setup_jinja2_i18n,
)
from birdnetpi.utils.file_path_resolver import FilePathResolver


@pytest.fixture
def mock_file_resolver():
    """Create a mock FilePathResolver."""
    mock_resolver = MagicMock(spec=FilePathResolver)
    mock_resolver.get_locales_dir.return_value = "locales"
    return mock_resolver


@pytest.fixture
def translation_manager(mock_file_resolver):
    """Create a TranslationManager instance for testing."""
    return TranslationManager(mock_file_resolver)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request."""
    request = MagicMock(spec=Request)
    request.headers = {"Accept-Language": "en-US,en;q=0.9,es;q=0.8"}
    return request


@pytest.fixture
def mock_app_with_translation_manager(translation_manager):
    """Create a mock app with translation manager."""
    app = MagicMock()
    app.state.translation_manager = translation_manager
    return app


class TestTranslationManager:
    """Test TranslationManager functionality."""

    def test_init(self, mock_file_resolver):
        """Should initialize with file resolver and default settings."""
        manager = TranslationManager(mock_file_resolver)

        assert manager.file_resolver == mock_file_resolver
        assert manager.locales_dir == "locales"
        assert manager.translations == {}
        assert manager.default_language == "en"

    @patch("birdnetpi.managers.translation_manager.translation")
    def test_get_translation(self, mock_translation_func, translation_manager):
        """Should get translation for specified language."""
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.return_value = mock_trans

        result = translation_manager.get_translation("es")

        assert result == mock_trans
        assert translation_manager.translations["es"] == mock_trans
        mock_translation_func.assert_called_once_with(
            "messages", localedir="locales", languages=["es"], fallback=True
        )

    @patch("birdnetpi.managers.translation_manager.translation")
    def test_get_translation_cached(self, mock_translation_func, translation_manager):
        """Should return cached translation on subsequent calls."""
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        translation_manager.translations["es"] = mock_trans

        result = translation_manager.get_translation("es")

        assert result == mock_trans
        mock_translation_func.assert_not_called()

    @patch("birdnetpi.managers.translation_manager.translation")
    def test_get_translation_file_not_found_fallback(
        self, mock_translation_func, translation_manager
    ):
        """Should fallback to default language when translation file not found."""
        mock_default_trans = MagicMock(spec=gettext.GNUTranslations)

        # First call raises FileNotFoundError, second call returns default translation
        mock_translation_func.side_effect = [
            FileNotFoundError("Translation file not found"),
            mock_default_trans,
        ]

        result = translation_manager.get_translation("fr")

        assert result == mock_default_trans
        assert translation_manager.translations["fr"] == mock_default_trans

        # Should have been called twice - first with 'fr', then with 'en'
        assert mock_translation_func.call_count == 2
        first_call, second_call = mock_translation_func.call_args_list

        assert first_call[1]["languages"] == ["fr"]
        assert second_call[1]["languages"] == ["en"]

    def test_install_for_request_default_language(self, translation_manager, mock_request):
        """Should install translation for request with default language parsing."""
        mock_request.headers = {"Accept-Language": "en-US,en;q=0.9"}
        mock_trans = MagicMock(spec=gettext.GNUTranslations)

        with patch.object(
            translation_manager, "get_translation", return_value=mock_trans
        ) as mock_get:
            result = translation_manager.install_for_request(mock_request)

            assert result == mock_trans
            mock_get.assert_called_once_with("en")
            mock_trans.install.assert_called_once()

    def test_install_for_request_spanish_language(self, translation_manager, mock_request):
        """Should install translation for Spanish language."""
        mock_request.headers = {"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}
        mock_trans = MagicMock(spec=gettext.GNUTranslations)

        with patch.object(
            translation_manager, "get_translation", return_value=mock_trans
        ) as mock_get:
            result = translation_manager.install_for_request(mock_request)

            assert result == mock_trans
            mock_get.assert_called_once_with("es")
            mock_trans.install.assert_called_once()

    def test_install_for_request__no_accept_language_header(
        self, translation_manager, mock_request
    ):
        """Should use default language when no Accept-Language header."""
        mock_request.headers = {}
        mock_trans = MagicMock(spec=gettext.GNUTranslations)

        with patch.object(
            translation_manager, "get_translation", return_value=mock_trans
        ) as mock_get:
            result = translation_manager.install_for_request(mock_request)

            assert result == mock_trans
            mock_get.assert_called_once_with("en")  # default language
            mock_trans.install.assert_called_once()

    def test_install_for_request_complex_accept_language(self, translation_manager, mock_request):
        """Should parse complex Accept-Language header correctly."""
        mock_request.headers = {"Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"}
        mock_trans = MagicMock(spec=gettext.GNUTranslations)

        with patch.object(
            translation_manager, "get_translation", return_value=mock_trans
        ) as mock_get:
            result = translation_manager.install_for_request(mock_request)

            assert result == mock_trans
            mock_get.assert_called_once_with("fr")  # Should extract 'fr' from 'fr-FR'
            mock_trans.install.assert_called_once()


class TestGetTranslationDependency:
    """Test get_translation FastAPI dependency function."""

    def test_get_translation_dependency(
        self, translation_manager, mock_app_with_translation_manager
    ):
        """Should get translation from request app state."""
        mock_request = MagicMock(spec=Request)
        mock_request.app = mock_app_with_translation_manager
        mock_trans = MagicMock(spec=gettext.GNUTranslations)

        with patch.object(
            translation_manager, "install_for_request", return_value=mock_trans
        ) as mock_install:
            result = get_translation(mock_request)

            assert result == mock_trans
            mock_install.assert_called_once_with(mock_request)


class TestJinja2Integration:
    """Test Jinja2 template integration functions."""

    def test_setup_jinja2_i18n(self):
        """Should setup Jinja2 templates with i18n functions."""
        mock_templates = MagicMock(spec=Jinja2Templates)
        mock_env = MagicMock()
        mock_templates.env = mock_env
        mock_env.globals = {}

        with patch("birdnetpi.managers.translation_manager.ngettext") as mock_ngettext:
            setup_jinja2_i18n(mock_templates)

            # Check that template globals were set
            assert "_" in mock_env.globals
            assert "gettext" in mock_env.globals
            assert "ngettext" in mock_env.globals
            assert mock_env.globals["ngettext"] == mock_ngettext

    def test_jinja2_get_text_function(self):
        """Should create get_text function that uses global _."""
        mock_templates = MagicMock(spec=Jinja2Templates)
        mock_env = MagicMock()
        mock_templates.env = mock_env
        mock_env.globals = {}

        with patch("birdnetpi.managers.translation_manager._") as mock_gettext:
            mock_gettext.return_value = "translated message"

            setup_jinja2_i18n(mock_templates)

            # Get the get_text function that was assigned to templates
            get_text_func = mock_env.globals["_"]

            # Test that it calls the global _ function
            result = get_text_func("Hello")
            assert result == "translated message"
            mock_gettext.assert_called_once_with("Hello")

    def test_jinja2_gettext_alias(self):
        """Should setup gettext as alias for _ function."""
        mock_templates = MagicMock(spec=Jinja2Templates)
        mock_env = MagicMock()
        mock_templates.env = mock_env
        mock_env.globals = {}

        setup_jinja2_i18n(mock_templates)

        # Both _ and gettext should be the same function
        assert mock_env.globals["_"] == mock_env.globals["gettext"]


class TestTranslationIntegration:
    """Integration tests for translation functionality."""

    @patch("birdnetpi.managers.translation_manager.translation")
    def test_end_to_end_translation_flow(self, mock_translation_func, mock_file_resolver):
        """Should handle complete translation flow from request to installation."""
        # Setup
        manager = TranslationManager(mock_file_resolver)
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.return_value = mock_trans

        # Create request with Spanish preference
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"Accept-Language": "es-MX,es;q=0.9,en;q=0.8"}

        # Execute translation installation
        result = manager.install_for_request(mock_request)

        # Verify
        assert result == mock_trans
        mock_translation_func.assert_called_once_with(
            "messages", localedir="locales", languages=["es"], fallback=True
        )
        mock_trans.install.assert_called_once()

        # Translation should be cached
        assert manager.translations["es"] == mock_trans

    def test_language_code_extraction_edge_cases(self, translation_manager):
        """Should handle various Accept-Language header formats."""
        test_cases = [
            ("en", "en"),
            ("en-US", "en"),
            ("es-ES,es;q=0.9", "es"),
            ("fr-CA,fr;q=0.8,en;q=0.7", "fr"),
            ("zh-CN,zh;q=0.9,en;q=0.8", "zh"),
            ("", "en"),  # Default fallback
        ]

        for accept_language, expected_lang in test_cases:
            mock_request = MagicMock(spec=Request)
            mock_request.headers = {"Accept-Language": accept_language} if accept_language else {}
            mock_trans = MagicMock(spec=gettext.GNUTranslations)

            with patch.object(
                translation_manager, "get_translation", return_value=mock_trans
            ) as mock_get:
                translation_manager.install_for_request(mock_request)
                mock_get.assert_called_with(expected_lang)

    @patch("birdnetpi.managers.translation_manager.translation")
    def test_fallback_chain(self, mock_translation_func, translation_manager):
        """Should handle fallback from missing language to default."""
        # First call fails, second succeeds with default
        mock_default_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.side_effect = [
            FileNotFoundError("No German translation"),
            mock_default_trans,
        ]

        result = translation_manager.get_translation("de")

        assert result == mock_default_trans
        assert mock_translation_func.call_count == 2

        # Verify fallback was attempted
        calls = mock_translation_func.call_args_list
        assert calls[0][1]["languages"] == ["de"]
        assert calls[1][1]["languages"] == ["en"]
