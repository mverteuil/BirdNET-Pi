"""Tests for TranslationManager."""

import gettext
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from starlette.templating import Jinja2Templates

from birdnetpi.i18n.translation_manager import (
    TranslationManager,
    get_translation,
    setup_jinja2_i18n,
)


@pytest.fixture
def mock_path_resolver(path_resolver, tmp_path):
    """Create a mock PathResolver.

    Uses the global path_resolver fixture as a base to prevent MagicMock file creation.
    """
    locales_dir = tmp_path / "locales"
    locales_dir.mkdir(parents=True, exist_ok=True)
    path_resolver.get_locales_dir = lambda: str(locales_dir)
    return path_resolver


@pytest.fixture
def translation_manager(mock_path_resolver):
    """Create a TranslationManager instance for testing."""
    return TranslationManager(mock_path_resolver)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request."""
    request = MagicMock(spec=Request, headers={"Accept-Language": "en-US,en;q=0.9,es;q=0.8"})
    request.query_params.get.return_value = None
    return request


@pytest.fixture
def mock_app_with_translation_manager(translation_manager):
    """Create a mock app with translation manager."""
    app = MagicMock(spec=FastAPI)
    # Use configure_mock to bypass spec checking for state attribute
    state_mock = MagicMock(spec=object)
    state_mock.translation_manager = translation_manager
    app.configure_mock(state=state_mock)
    return app


class TestTranslationManager:
    """Test TranslationManager functionality."""

    def test_init(self, path_resolver):
        """Should initialize with file resolver and default settings."""
        manager = TranslationManager(path_resolver)
        assert manager.path_resolver == path_resolver
        assert manager.locales_dir == path_resolver.get_locales_dir()
        assert manager.translations == {}
        assert manager.default_language == "en"

    @patch("birdnetpi.i18n.translation_manager.translation", autospec=True)
    def test_get_translation(self, mock_translation_func, translation_manager):
        """Should get translation for specified language."""
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.return_value = mock_trans
        result = translation_manager.get_translation("es")
        assert result == mock_trans
        assert translation_manager.translations["es"] == mock_trans
        mock_translation_func.assert_called_once()
        call_args = mock_translation_func.call_args
        assert call_args[1]["languages"] == ["es"]
        assert call_args[1]["fallback"] is True
        assert "locales" in str(call_args[1]["localedir"])

    @patch("birdnetpi.i18n.translation_manager.translation", autospec=True)
    def test_get_translation_cached(self, mock_translation_func, translation_manager):
        """Should return cached translation on subsequent calls."""
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        translation_manager.translations["es"] = mock_trans
        result = translation_manager.get_translation("es")
        assert result == mock_trans
        mock_translation_func.assert_not_called()

    @patch("birdnetpi.i18n.translation_manager.translation", autospec=True)
    def test_get_translation_file_not_found_fallback(
        self, mock_translation_func, translation_manager
    ):
        """Should fallback to default language when translation file not found."""
        mock_default_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.side_effect = [
            FileNotFoundError("Translation file not found"),
            mock_default_trans,
        ]
        result = translation_manager.get_translation("fr")
        assert result == mock_default_trans
        assert translation_manager.translations["fr"] == mock_default_trans
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
            mock_get.assert_called_once_with("en")
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
            mock_get.assert_called_once_with("fr")
            mock_trans.install.assert_called_once()


class TestGetTranslationDependency:
    """Test get_translation FastAPI dependency function."""

    def test_get_translation_dependency(
        self, translation_manager, mock_app_with_translation_manager
    ):
        """Should get translation from request app state."""
        mock_request = MagicMock(spec=Request, app=mock_app_with_translation_manager)
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
        mock_env = MagicMock(spec=object)
        mock_env.globals = {}
        mock_templates = MagicMock(spec=Jinja2Templates, env=mock_env)
        with patch("birdnetpi.i18n.translation_manager.ngettext", autospec=True) as mock_ngettext:
            setup_jinja2_i18n(mock_templates)
            assert "_" in mock_env.globals
            assert "gettext" in mock_env.globals
            assert "ngettext" in mock_env.globals
            assert mock_env.globals["ngettext"] == mock_ngettext

    def test_jinja2_get_text_function(self):
        """Should create get_text function that uses global _."""
        mock_env = MagicMock(spec=object)
        mock_env.globals = {}
        mock_templates = MagicMock(spec=Jinja2Templates, env=mock_env)
        with patch("builtins._", create=True) as mock_gettext:
            mock_gettext.return_value = "translated message"
            setup_jinja2_i18n(mock_templates)
            get_text_func = mock_env.globals["_"]
            result = get_text_func("Hello")
            assert result == "translated message"
            mock_gettext.assert_called_once_with("Hello")

    def test_jinja2_gettext_alias(self):
        """Should setup gettext as alias for _ function."""
        mock_env = MagicMock(spec=object)
        mock_env.globals = {}
        mock_templates = MagicMock(spec=Jinja2Templates, env=mock_env)
        setup_jinja2_i18n(mock_templates)
        assert mock_env.globals["_"] == mock_env.globals["gettext"]


class TestTranslationIntegration:
    """Integration tests for translation functionality."""

    @patch("birdnetpi.i18n.translation_manager.translation", autospec=True)
    def test_end_to_end_translation_flow(self, mock_translation_func, mock_path_resolver):
        """Should handle complete translation flow from request to installation."""
        manager = TranslationManager(mock_path_resolver)
        mock_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.return_value = mock_trans
        mock_request = MagicMock(
            spec=Request, headers={"Accept-Language": "es-MX,es;q=0.9,en;q=0.8"}
        )
        mock_request.query_params.get.return_value = None
        result = manager.install_for_request(mock_request)
        assert result == mock_trans
        mock_translation_func.assert_called_once()
        call_args = mock_translation_func.call_args
        assert call_args[1]["languages"] == ["es"]
        assert call_args[1]["fallback"] is True
        assert "locales" in str(call_args[1]["localedir"])
        mock_trans.install.assert_called_once()
        assert manager.translations["es"] == mock_trans

    def test_language_code_extraction_edge_cases(self, translation_manager):
        """Should handle various Accept-Language header formats."""
        test_cases = [
            ("en", "en"),
            ("en-US", "en"),
            ("es-ES,es;q=0.9", "es"),
            ("fr-CA,fr;q=0.8,en;q=0.7", "fr"),
            ("zh-CN,zh;q=0.9,en;q=0.8", "zh"),
            ("", "en"),
        ]
        for accept_language, expected_lang in test_cases:
            mock_request = MagicMock(spec=Request)
            mock_request.headers = {"Accept-Language": accept_language} if accept_language else {}
            mock_request.query_params.get.return_value = None
            mock_trans = MagicMock(spec=gettext.GNUTranslations)
            with patch.object(
                translation_manager, "get_translation", return_value=mock_trans
            ) as mock_get:
                translation_manager.install_for_request(mock_request)
                mock_get.assert_called_with(expected_lang)

    @patch("birdnetpi.i18n.translation_manager.translation", autospec=True)
    def test_fallback_chain(self, mock_translation_func, translation_manager):
        """Should handle fallback from missing language to default."""
        mock_default_trans = MagicMock(spec=gettext.GNUTranslations)
        mock_translation_func.side_effect = [
            FileNotFoundError("No German translation"),
            mock_default_trans,
        ]
        result = translation_manager.get_translation("de")
        assert result == mock_default_trans
        assert mock_translation_func.call_count == 2
        calls = mock_translation_func.call_args_list
        assert calls[0][1]["languages"] == ["de"]
        assert calls[1][1]["languages"] == ["en"]
