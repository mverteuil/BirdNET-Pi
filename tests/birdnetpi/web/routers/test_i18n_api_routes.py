"""Tests for i18n API routes that provide translations for JavaScript."""

from unittest.mock import MagicMock

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.i18n.translation_manager import TranslationManager
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.i18n_api_routes import router


@pytest.fixture
def mock_translation_manager():
    """Create a mock translation manager."""
    manager = MagicMock(spec=TranslationManager)

    # Create simple classes for mocking
    class MockMessage:
        def __init__(self):
            self.id = "test_key"
            self.string = "test_value"

    class MockTranslation:
        """Spec class for translation object."""

        def gettext(self, msgid: str) -> str:
            return ""

        @property
        def _catalog(self):
            return []

    # Create a mock translation object with proper spec
    mock_translation = MagicMock(spec=MockTranslation)
    mock_translation.gettext.side_effect = lambda x: f"translated:{x}"
    mock_translation._catalog = [MockMessage()]

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
    client = TestClient(app)
    client.mock_translation_manager = mock_translation_manager  # type: ignore[attr-defined]
    return client


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

        # Audio/connection messages
        assert "audio-not-available" in translations
        assert "connect-audio" in translations
        assert "disconnect-audio" in translations

        # Time periods
        assert "today" in translations
        assert "last-7-days" in translations
        assert "last-30-days" in translations
        assert "all-time" in translations

        # Filters and selections
        assert "all-families" in translations
        assert "all-genera" in translations
        assert "all-species" in translations
        assert "select-family" in translations
        assert "select-genus" in translations

        # Loading states
        assert "loading" in translations
        assert "checking" in translations
        assert "error" in translations
        assert "error-genera" in translations
        assert "error-species" in translations

        # Taxonomy labels
        assert "family" in translations
        assert "genus" in translations
        assert "species" in translations

        # Actions
        assert "play-recording" in translations
        assert "filter-by-genus" in translations
        assert "filter-by-species" in translations
        assert "filter-by-family" in translations

        # Statistics
        assert "recordings" in translations
        assert "species-count" in translations
        assert "detections" in translations
        assert "average-confidence" in translations
        assert "date-range" in translations

        # Update messages
        assert "check-for-updates" in translations
        assert "update-available" in translations
        assert "up-to-date" in translations
        assert "starting-test-update" in translations
        assert "starting-update" in translations
        assert "update-cancelled" in translations

        # Configuration messages
        assert "discard-changes" in translations
        assert "config-saved" in translations
        assert "save-failed" in translations
        assert "saved-status" in translations
        assert "save-failed-status" in translations
        assert "reset-success" in translations
        assert "validation-passed" in translations
        assert "validation-error" in translations
        assert "modified-status" in translations
        assert "ready-status" in translations
        assert "modified-valid-status" in translations

        # Error messages
        assert "invalid-remote-format" in translations
        assert "invalid-branch-format" in translations
        assert "failed-to-save-config" in translations
        assert "failed-to-check-updates" in translations
        assert "failed-to-apply-update" in translations
        assert "failed-to-cancel-update" in translations
        assert "failed-to-save-git-config" in translations

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

        # Create a spec class without _catalog
        class MockTranslationNoCatalog:
            """Spec class for translation without catalog."""

            def gettext(self, msgid: str) -> str:
                return ""

        # Create a translation without _catalog attribute
        mock_translation = MagicMock(spec=MockTranslationNoCatalog)
        mock_translation.gettext.side_effect = lambda x: f"translated:{x}"

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
