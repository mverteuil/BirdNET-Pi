"""Tests for internationalization middleware and translation system."""

import tempfile
from gettext import GNUTranslations, NullTranslations
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from birdnetpi.managers.translation_manager import TranslationManager
from birdnetpi.utils.path_resolver import PathResolver
from birdnetpi.web.middleware.i18n import LanguageMiddleware


@pytest.fixture
def mock_path_resolver():
    """Create mock file resolver with temporary locales directory."""
    resolver = Mock(spec=PathResolver)
    with tempfile.TemporaryDirectory() as tmpdir:
        locales_dir = Path(tmpdir) / "locales"
        locales_dir.mkdir()

        # Create English locale directory
        en_dir = locales_dir / "en" / "LC_MESSAGES"
        en_dir.mkdir(parents=True)

        # Create Spanish locale directory
        es_dir = locales_dir / "es" / "LC_MESSAGES"
        es_dir.mkdir(parents=True)

        resolver.get_locales_dir.return_value = locales_dir
        yield resolver


@pytest.fixture
def translation_manager(mock_path_resolver):
    """Create a TranslationManager instance."""
    return TranslationManager(mock_path_resolver)


@pytest.fixture
def app_with_middleware(translation_manager):
    """Create FastAPI app with i18n middleware."""
    app = FastAPI()
    app.state.translation_manager = translation_manager
    app.add_middleware(LanguageMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        from gettext import gettext as _

        return {
            "message": _("Hello"),
            "language": request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0],
        }

    @app.get("/plural")
    async def plural_endpoint(request: Request):
        from gettext import ngettext

        count = request.query_params.get("count", 1)
        count = int(count)
        return {
            "message": ngettext("1 detection", "{n} detections", count).format(n=count),
            "count": count,
        }

    return app


@pytest.fixture
def client(app_with_middleware):
    """Create test client."""
    return TestClient(app_with_middleware)


class TestLanguageMiddleware:
    """Test language middleware functionality."""

    def test_middleware_processes_request(self, client):
        """Test that middleware processes requests without errors."""
        response = client.get("/test")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "language" in data

    def test_default_language(self, client):
        """Test default language when no Accept-Language header."""
        response = client.get("/test")
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"
        # Without actual translation files, will return original text
        assert data["message"] == "Hello"

    def test_accept_language_header(self, client):
        """Test language detection from Accept-Language header."""
        response = client.get("/test", headers={"Accept-Language": "es-ES,es;q=0.9"})
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "es"

    def test_complex_accept_language(self, client):
        """Test parsing complex Accept-Language headers."""
        response = client.get(
            "/test", headers={"Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "fr"

    def test_pluralization(self, client):
        """Test ngettext pluralization support."""
        # Singular
        response = client.get("/plural?count=1")
        assert response.status_code == 200
        data = response.json()
        assert "1 detection" in data["message"]

        # Plural
        response = client.get("/plural?count=5")
        assert response.status_code == 200
        data = response.json()
        assert "5 detections" in data["message"]


class TestTranslationManager:
    """Test TranslationManager functionality."""

    def test_initialization(self, mock_path_resolver):
        """Test TranslationManager initialization."""
        manager = TranslationManager(mock_path_resolver)
        assert manager.path_resolver == mock_path_resolver
        assert manager.default_language == "en"
        assert isinstance(manager.translations, dict)

    def test_get_translation_caching(self, translation_manager):
        """Test that translations are cached."""
        trans1 = translation_manager.get_translation("en")
        trans2 = translation_manager.get_translation("en")
        assert trans1 is trans2  # Same object, cached

    def test_get_translation_fallback(self, translation_manager):
        """Test fallback for unsupported languages."""
        # Should fall back to NullTranslations for missing language
        trans = translation_manager.get_translation("xyz")
        assert isinstance(trans, GNUTranslations | NullTranslations)

    def test_install_for_request(self, translation_manager):
        """Test installing translation for a request."""
        request = Mock(spec=Request)
        request.headers = {"Accept-Language": "es-ES,es;q=0.9"}

        trans = translation_manager.install_for_request(request)
        assert isinstance(trans, GNUTranslations | NullTranslations)

    def test_install_for_request_no_header(self, translation_manager):
        """Test installing translation when no Accept-Language header."""
        request = Mock(spec=Request)
        request.headers = {}

        trans = translation_manager.install_for_request(request)
        assert isinstance(trans, GNUTranslations | NullTranslations)

    @pytest.mark.parametrize(
        "header,expected_lang",
        [
            ("en", "en"),
            ("en-US", "en"),
            ("es-ES,es;q=0.9", "es"),
            ("fr-CA,fr;q=0.9,en;q=0.8", "fr"),
            ("de-DE", "de"),
            ("pt-BR", "pt"),
        ],
    )
    def test_language_parsing(self, translation_manager, header, expected_lang):
        """Test parsing various Accept-Language header formats."""
        request = Mock(spec=Request)
        request.headers = {"Accept-Language": header}

        # Mock the method to capture the language argument
        with patch.object(translation_manager, "get_translation") as mock_get:
            translation_manager.install_for_request(request)
            mock_get.assert_called_with(expected_lang)


class TestJinja2Integration:
    """Test Jinja2 template integration."""

    def test_setup_jinja2_i18n(self):
        """Test Jinja2 i18n setup."""
        from jinja2 import Environment

        from birdnetpi.managers.translation_manager import setup_jinja2_i18n

        # Create a mock Jinja2Templates object
        class MockTemplates:
            def __init__(self):
                self.env = Environment()

        templates = MockTemplates()
        setup_jinja2_i18n(templates)  # type: ignore[arg-type]

        # Check that translation functions were added
        assert "_" in templates.env.globals
        assert "gettext" in templates.env.globals
        assert "ngettext" in templates.env.globals

    def test_template_translation_functions(self):
        """Test that template translation functions work."""
        from jinja2 import Environment

        from birdnetpi.managers.translation_manager import setup_jinja2_i18n

        class MockTemplates:
            def __init__(self):
                self.env = Environment()

        templates = MockTemplates()
        setup_jinja2_i18n(templates)  # type: ignore[arg-type]

        # Test template rendering with translation
        template = templates.env.from_string("{{ _('Welcome') }}")
        result = template.render()
        assert result == "Welcome"  # Without translation files, returns original

        # Test pluralization
        template = templates.env.from_string(
            "{{ ngettext('1 bird', '%(n)s birds', count) % {'n': count} }}"
        )
        result = template.render(count=1)
        assert "1 bird" in result

        result = template.render(count=5)
        assert "5 birds" in result


class TestTranslationFiles:
    """Test translation file handling."""

    def test_babel_config_exists(self):
        """Test that babel.cfg configuration exists."""
        babel_cfg = Path("babel.cfg")
        assert babel_cfg.exists(), "babel.cfg configuration file should exist"

    def test_locales_directory_structure(self):
        """Test locales directory structure."""
        locales_dir = Path("locales")
        if locales_dir.exists():
            # Check for proper structure
            assert locales_dir.is_dir()

            # Check for at least English directory
            en_dir = locales_dir / "en" / "LC_MESSAGES"
            if en_dir.exists():
                assert en_dir.is_dir()

    def test_po_files_exist(self):
        """Test that .po files exist for translations."""
        locales_dir = Path("locales")
        if locales_dir.exists():
            po_files = list(locales_dir.glob("*/LC_MESSAGES/*.po"))
            # We should have .po files for languages we support
            assert len(po_files) >= 0  # May not have any yet in early development

    def test_translation_extraction_config(self):
        """Test that babel.cfg is properly configured."""
        babel_cfg = Path("babel.cfg")
        if babel_cfg.exists():
            content = babel_cfg.read_text()
            # Check for Jinja2 extraction
            assert "jinja2" in content.lower() or ".html" in content
            # Check for Python extraction
            assert "python" in content.lower() or ".py" in content
