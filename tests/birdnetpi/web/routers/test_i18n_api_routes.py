"""Tests for i18n API routes that provide translations for JavaScript."""

from gettext import GNUTranslations
from unittest.mock import MagicMock

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.i18n_api_routes import router


class MockCatalogMessage:
    """Simple catalog message for testing."""

    def __init__(self, msg_id: str, msg_str: str):
        self.id = msg_id
        self.string = msg_str


@pytest.fixture
def mock_translation_manager():
    """Create a mock translation manager."""
    manager = MagicMock(spec=TranslationManager)

    # Use actual GNUTranslations type for better type safety
    mock_translation = MagicMock(spec=GNUTranslations)
    mock_translation.gettext.side_effect = lambda x: f"translated:{x}"
    # Add _catalog attribute (not part of GNUTranslations interface but used by our code)
    mock_translation._catalog = [MockCatalogMessage("test_key", "test_value")]

    manager.get_translation.return_value = mock_translation
    return manager


@pytest.fixture
def client(mock_translation_manager):
    """Create test client with i18n API routes and mocked dependencies."""
    app = FastAPI()
    container = Container()
    container.translation_manager.override(providers.Singleton(lambda: mock_translation_manager))
    container.wire(modules=["birdnetpi.web.routers.i18n_api_routes"])
    app.include_router(router, prefix="/api")

    # Store mock on app state for type safety
    test_client = TestClient(app)
    app.state.mock_translation_manager = mock_translation_manager

    # Provide access via a property-like access pattern
    test_client.mock_translation_manager = mock_translation_manager  # type: ignore[attr-defined]
    return test_client


class TestI18nAPIRoutes:
    """Test i18n API endpoints."""

    def test_get_translations_json_with_explicit_lang(self, client):
        """Should get translations with explicit language parameter."""
        response = client.get("/api/i18n/translations?lang=fr")

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "fr"
        assert "translations" in data
        assert isinstance(data["translations"], dict)

        # Verify it contains expected translation keys
        assert "audio-not-available" in data["translations"]
        assert "connect-audio" in data["translations"]
        assert "disconnect-audio" in data["translations"]
        assert "today" in data["translations"]
        assert "last-7-days" in data["translations"]

        # Verify the translation manager was called with correct language
        client.mock_translation_manager.get_translation.assert_called_with("fr")

    def test_get_translations_json_from_accept_language_header(self, client):
        """Should get translations from Accept-Language header."""
        response = client.get(
            "/api/i18n/translations", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "de"  # Should extract first language code
        assert "translations" in data

        # Verify the translation manager was called with extracted language
        client.mock_translation_manager.get_translation.assert_called_with("de")

    def test_get_translations_json_defaults_to_en(self, client):
        """Should default to English when no header present."""
        response = client.get("/api/i18n/translations")

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"

        # Verify the translation manager was called with default language
        client.mock_translation_manager.get_translation.assert_called_with("en")

    def test_get_translations_json_contains_all_required_keys(self, client):
        """Should contain all required JavaScript translation keys."""
        response = client.get("/api/i18n/translations?lang=en")

        assert response.status_code == 200
        data = response.json()
        translations = data["translations"]

        # Verify critical translation keys exist (sampling approach)
        # Audio/connection messages
        assert "audio-not-available" in translations
        assert "connect-audio" in translations
        assert "disconnect-audio" in translations

        # Time periods
        assert "today" in translations
        assert "last-7-days" in translations

        # Essential keys for app functionality
        assert "loading" in translations
        assert "error" in translations
        assert "detections" in translations

    def test_translations_calls_gettext_with_correct_source_strings(self, client):
        """Should call gettext with correct English source strings."""
        # Reset mock to track calls
        mock_translation = client.mock_translation_manager.get_translation.return_value
        mock_translation.gettext.reset_mock()

        response = client.get("/api/i18n/translations?lang=fr")

        assert response.status_code == 200

        # Verify gettext was called (translations are happening)
        assert mock_translation.gettext.call_count > 0

        # Get all the source strings that were requested for translation
        call_args = [call[0][0] for call in mock_translation.gettext.call_args_list]

        # Verify some critical translations were requested with correct English source strings
        # These should match the actual msgid values from the source code (lines 48-112)
        assert "Audio not available" in call_args
        assert "Connect Audio" in call_args
        assert "Today" in call_args
        assert "Loading..." in call_args

        # Verify the response uses the translated values
        data = response.json()
        assert data["translations"]["audio-not-available"] == "translated:Audio not available"

    def test_get_language_catalog(self, client):
        """Should get full language catalog."""
        response = client.get("/api/catalog/fr")

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "fr"
        assert "catalog" in data
        assert isinstance(data["catalog"], dict)

        # Verify the translation manager was called
        client.mock_translation_manager.get_translation.assert_called_with("fr")

    def test_get_language_catalog_contains_catalog_entries(self, client):
        """Should contain entries from translation catalog."""
        response = client.get("/api/catalog/en")

        assert response.status_code == 200
        data = response.json()
        catalog = data["catalog"]

        # Should contain the mock message we set up
        assert "test_key" in catalog
        assert catalog["test_key"] == "test_value"

    def test_get_language_catalog_handles_missing_catalog(self, client):
        """Should handle translation without _catalog attribute."""
        # Create a translation using GNUTranslations (which doesn't have _catalog by default)
        mock_translation = MagicMock(spec=GNUTranslations)
        mock_translation.gettext.side_effect = lambda x: f"translated:{x}"
        # Explicitly ensure _catalog doesn't exist
        del mock_translation._catalog

        client.mock_translation_manager.get_translation.return_value = mock_translation

        response = client.get("/api/catalog/en")

        assert response.status_code == 200
        data = response.json()
        assert data["catalog"] == {}  # Should return empty catalog

    def test_get_language_catalog_different_languages(self, client):
        """Should get catalogs for different languages."""
        languages = ["en", "fr", "de", "es", "ja"]

        for lang in languages:
            response = client.get(f"/api/catalog/{lang}")
            assert response.status_code == 200
            data = response.json()
            assert data["language"] == lang
            client.mock_translation_manager.get_translation.assert_called_with(lang)

    def test_translations_response_model_structure(self, client):
        """Should match expected Pydantic model structure."""
        response = client.get("/api/i18n/translations?lang=en")

        assert response.status_code == 200
        data = response.json()

        # Verify top-level structure
        assert set(data.keys()) == {"language", "translations"}
        assert isinstance(data["language"], str)
        assert isinstance(data["translations"], dict)

        # Verify all translation values are strings
        for key, value in data["translations"].items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    def test_catalog_response_model_structure(self, client):
        """Should match expected catalog Pydantic model structure."""
        response = client.get("/api/catalog/en")

        assert response.status_code == 200
        data = response.json()

        # Verify top-level structure
        assert set(data.keys()) == {"language", "catalog"}
        assert isinstance(data["language"], str)
        assert isinstance(data["catalog"], dict)

    def test_accept_language_parsing_edge_cases(self, client):
        """Should correctly parse various Accept-Language header formats."""
        # Test different header formats
        test_cases = [
            ("en-US", "en"),  # Standard format with region
            ("en", "en"),  # Just language code
            ("en-US,fr-FR;q=0.8", "en"),  # Multiple with quality values
            ("de-DE,de;q=0.9,en;q=0.8", "de"),  # Complex with multiple quality values
        ]

        for header, expected_lang in test_cases:
            response = client.get("/api/i18n/translations", headers={"Accept-Language": header})

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == expected_lang, f"Failed for header: {header}"
            # Verify translation manager was called with correct language
            client.mock_translation_manager.get_translation.assert_called_with(expected_lang)

    def test_accept_language_empty_returns_empty_string(self, client):
        """Should return empty language code when Accept-Language header is empty."""
        # This tests current behavior - empty header splits to empty string
        # In production, translation_manager would handle this (fallback to default)
        response = client.get("/api/i18n/translations", headers={"Accept-Language": ""})

        assert response.status_code == 200
        data = response.json()
        # Current implementation: "".split(",")[0].split("-")[0] == ""
        assert data["language"] == ""
        # Verify translation_manager was called with empty string
        client.mock_translation_manager.get_translation.assert_called_with("")
