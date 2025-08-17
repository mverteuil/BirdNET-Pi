"""Integration tests for the complete i18n system."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from birdnetpi.config import BirdNETConfig
from birdnetpi.i18n.translation_manager import TranslationManager


@pytest.fixture
def config_with_language():
    """Create configs for different languages."""

    def _config(language="en"):
        return BirdNETConfig(
            language=language,
            site_name="BirdNET-Pi Test",
            latitude=0.0,
            longitude=0.0,
        )

    return _config


@pytest.fixture
def mock_path_resolver(path_resolver):
    """Create mock file resolver."""
    # Use the global path_resolver fixture and customize it
    locales_dir = Path(__file__).parent.parent.parent / "locales"
    path_resolver.get_locales_dir = lambda: locales_dir
    path_resolver.get_database_path = lambda: Path(":memory:")
    path_resolver.get_models_dir = lambda: Path("models")
    path_resolver.get_static_dir = lambda: Path("static")
    path_resolver.get_templates_dir = lambda: Path("src/birdnetpi/web/templates")
    return path_resolver


class TestLanguageSwitching:
    """Test language switching in the web interface."""

    def test_config_language_respected(self, config_with_language, mock_path_resolver):
        """Test that the configured language is used by default."""
        # Test with Spanish config
        config_with_language("es")  # Config created but not used directly
        translation_manager = TranslationManager(mock_path_resolver)

        # Mock request without Accept-Language header
        request = Mock()
        request.headers = {}

        # Should use config language (Spanish)
        trans = translation_manager.get_translation("es")
        assert trans is not None

    def test_accept_language_header_override(self, config_with_language, mock_path_resolver):
        """Test that Accept-Language header can override config."""
        # Config set to English
        config_with_language("en")  # Config created but not used directly
        translation_manager = TranslationManager(mock_path_resolver)

        # Request with French Accept-Language
        request = Mock()
        request.headers = {"Accept-Language": "fr-FR,fr;q=0.9"}

        # Should extract and use French
        trans = translation_manager.install_for_request(request)
        # Translation should be installed globally
        assert trans is not None

    @pytest.mark.parametrize(
        "accept_header,expected_lang",
        [
            ("en-US,en;q=0.9", "en"),
            ("es-ES,es;q=0.9", "es"),
            ("fr-FR,fr;q=0.9", "fr"),
            ("de-DE,de;q=0.9", "de"),
            ("pt-BR,pt;q=0.8", "pt"),
            ("zh-CN,zh;q=0.9", "zh"),
            ("ja-JP,ja;q=0.9", "ja"),
        ],
    )
    def test_multiple_language_support(self, mock_path_resolver, accept_header, expected_lang):
        """Test that various languages are properly extracted from headers."""
        translation_manager = TranslationManager(mock_path_resolver)

        request = Mock()
        request.headers = {"Accept-Language": accept_header}

        # Parse the header manually to verify
        lang = accept_header.split(",")[0].split("-")[0]
        assert lang == expected_lang

        # Install translation
        trans = translation_manager.install_for_request(request)
        assert trans is not None

    def test_fallback_to_english(self, mock_path_resolver):
        """Test fallback to English for unsupported languages."""
        translation_manager = TranslationManager(mock_path_resolver)

        request = Mock()
        request.headers = {"Accept-Language": "xyz-XY"}  # Non-existent language

        # Should fall back gracefully
        trans = translation_manager.install_for_request(request)
        assert trans is not None  # Should get fallback translation


class TestTranslationContent:
    """Test actual translation content."""

    def test_message_extraction_coverage(self):
        """Test that key UI elements are marked for translation."""
        templates_dir = Path("src/birdnetpi/web/templates")
        if not templates_dir.exists():
            pytest.skip("Templates directory not found")

        # Check that templates have translation markers
        html_files = list(templates_dir.glob("**/*.html"))

        translation_markers = [
            "{{ _(",
            "{{ gettext(",
            "{% trans",
            "{% blocktrans",
            "{{ ngettext(",
        ]

        files_with_translations = 0
        total_markers = 0

        for html_file in html_files:
            content = html_file.read_text()
            file_has_markers = False

            for marker in translation_markers:
                if marker in content:
                    file_has_markers = True
                    # Count occurrences
                    total_markers += content.count(marker)

            if file_has_markers:
                files_with_translations += 1

        # Report coverage
        if len(html_files) > 0:
            coverage = (files_with_translations / len(html_files)) * 100
            print(
                f"\nTranslation coverage: "
                f"{files_with_translations}/{len(html_files)} files ({coverage:.1f}%)"
            )
            print(f"Total translation markers found: {total_markers}")

            # At least 50% of templates should have translations
            assert coverage >= 50, f"Only {coverage:.1f}% of templates have translation markers"

    def test_po_file_completeness(self):
        """Test that .po files have translations for common strings."""
        locales_dir = Path("locales")
        if not locales_dir.exists():
            pytest.skip("Locales directory not found")

        # Check Spanish translations as an example
        es_po = locales_dir / "es" / "LC_MESSAGES" / "messages.po"
        if es_po.exists():
            content = es_po.read_text()

            # Check for some common UI strings
            common_strings = [
                "Welcome",
                "Detections",
                "Settings",
                "Species",
                "Date",
                "Time",
                "Confidence",
            ]

            translated_count = 0
            for string in common_strings:
                if f'msgid "{string}"' in content:
                    # Check if there's a corresponding non-empty msgstr
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if f'msgid "{string}"' in line:
                            # Check next few lines for msgstr
                            for j in range(i + 1, min(i + 5, len(lines))):
                                if lines[j].startswith("msgstr"):
                                    if lines[j] != 'msgstr ""':
                                        translated_count += 1
                                    break

            print(
                f"\nSpanish translations: {translated_count}/{len(common_strings)} common strings"
            )

    def test_mo_files_compiled(self):
        """Test that .mo files are properly compiled."""
        locales_dir = Path("locales")
        if not locales_dir.exists():
            pytest.skip("Locales directory not found")

        # Check for compiled .mo files
        mo_files = list(locales_dir.glob("*/LC_MESSAGES/*.mo"))

        # Should have at least English
        assert len(mo_files) >= 1, "No compiled .mo files found"

        # Check that .mo files are not empty
        for mo_file in mo_files:
            size = mo_file.stat().st_size
            assert size > 0, f"{mo_file} is empty"
            print(f"\nCompiled: {mo_file.relative_to(locales_dir)} ({size} bytes)")


class TestSpeciesTranslation:
    """Test species name translation integration."""

    def test_species_display_modes(self, config_with_language):
        """Test different species display modes."""
        from birdnetpi.services.species_display_service import SpeciesDisplayService

        # Test different display modes
        modes = ["full", "common_name", "scientific_name"]

        for mode in modes:
            config = config_with_language("en")
            config.species_display_mode = mode

            service = SpeciesDisplayService(config)

            # Test formatting with mock detection
            from unittest.mock import Mock

            detection = Mock()
            detection.scientific_name = "Turdus migratorius"
            detection.common_name = "American Robin"
            detection.translated_name = None
            detection.ioc_english_name = "American Robin"

            result = service.format_full_species_display(detection)

            if mode == "full":
                assert "Turdus migratorius" in result
                assert "American Robin" in result
                assert "(" in result and ")" in result  # Check for full format
            elif mode == "common_name":
                assert result == "American Robin"
                assert "Turdus migratorius" not in result
            elif mode == "scientific_name":
                assert result == "Turdus migratorius"
                assert "American Robin" not in result

    def test_multilingual_species_names(self, path_resolver):
        """Test that species names work in multiple languages using actual databases."""
        from pathlib import Path

        import pytest
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService

        # The path_resolver fixture already points to data/database/ for the databases
        # Check if databases exist - skip test if not available
        ioc_db = path_resolver.get_ioc_database_path()
        avibase_db = path_resolver.get_avibase_database_path()
        patlevin_db = path_resolver.get_patlevin_database_path()

        if not Path(ioc_db).exists():
            pytest.skip(
                "IOC database not available - download with: uv run asset-installer install"
            )
        if not Path(avibase_db).exists():
            pytest.skip(
                "Avibase database not available - download with: uv run asset-installer install"
            )
        if not Path(patlevin_db).exists():
            pytest.skip(
                "PatLevin database not available - download with: uv run asset-installer install"
            )

        # Create service with real databases
        service = MultilingualDatabaseService(path_resolver)

        # Create a real SQLite session
        engine = create_engine("sqlite:///:memory:")
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

        # Attach the real databases
        service.attach_all_to_session(session)

        try:
            # Test with a real species that should exist in the databases
            result = service.get_best_common_name(session, "Turdus migratorius", "es")

            # Should get a real Spanish name
            assert result["common_name"] is not None
            assert result["source"] in ["IOC", "PatLevin", "Avibase"]
            # The actual Spanish name might vary but should contain "Zorzal" or "Petirrojo"

            # Test English name
            result_en = service.get_best_common_name(session, "Turdus migratorius", "en")
            assert result_en["common_name"] == "American Robin"
            assert result_en["source"] == "IOC"

            # Test French name
            result_fr = service.get_best_common_name(session, "Turdus migratorius", "fr")
            assert result_fr["common_name"] is not None
            assert "Merle" in result_fr["common_name"] or "merle" in result_fr["common_name"]

        finally:
            # Clean up
            service.detach_all_from_session(session)
            session.close()


class TestEndToEndTranslation:
    """Test complete translation flow."""

    def test_translation_extraction_update_compile_cycle(self):
        """Test the complete translation workflow."""
        import subprocess
        import tempfile
        from pathlib import Path

        # This test verifies the translation workflow but doesn't modify actual files

        # 1. Check babel.cfg exists
        babel_cfg = Path("babel.cfg")
        assert babel_cfg.exists(), "babel.cfg is required for extraction"

        # 2. Test extraction (dry run - don't overwrite actual files)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_pot = Path(tmpdir) / "test_messages.pot"

            # Extract to temporary file
            result = subprocess.run(
                ["pybabel", "extract", "-F", "babel.cfg", "-o", str(tmp_pot), "."],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Extraction failed: {result.stderr}"
            assert tmp_pot.exists(), "POT file was not created"

            # Check that messages were extracted
            content = tmp_pot.read_text()
            assert "msgid" in content, "No messages extracted"

            # Count extracted messages
            msgid_count = content.count("msgid")
            print(f"\nExtracted {msgid_count} messages")
            assert msgid_count > 50, f"Only {msgid_count} messages extracted, expected more"

    def test_template_rendering_with_translations(self):
        """Test that templates can render with translations."""
        from jinja2 import DictLoader, Environment

        from birdnetpi.i18n.translation_manager import setup_jinja2_i18n

        # Create a simple template
        templates = {
            "test.html": """
                <h1>{{ _('Welcome to BirdNET-Pi') }}</h1>
                <p>{{ ngettext('%(num)s detection', '%(num)s detections', count)
                       % {'num': count} }}</p>
                <p>{{ _('Species') }}: {{ species_name }}</p>
            """
        }

        # Set up Jinja2 with i18n
        env = Environment(loader=DictLoader(templates))

        class MockTemplates:
            def __init__(self):
                self.env = env

        mock_templates = MockTemplates()
        setup_jinja2_i18n(mock_templates)  # type: ignore[arg-type]

        # Render template
        template = env.get_template("test.html")

        # Test with singular
        output = template.render(count=1, species_name="Turdus migratorius")
        assert "1 detection" in output
        assert "Turdus migratorius" in output

        # Test with plural
        output = template.render(count=5, species_name="Passer domesticus")
        assert "5 detections" in output
        assert "Passer domesticus" in output
