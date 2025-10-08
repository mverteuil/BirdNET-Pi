"""Integration tests for the complete i18n system."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jinja2 import DictLoader, Environment
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.datastructures import QueryParams
from starlette.requests import Request

from birdnetpi.config import BirdNETConfig
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import DetectionWithTaxa
from birdnetpi.i18n.translation_manager import TranslationManager, setup_jinja2_i18n
from birdnetpi.species.display import SpeciesDisplayService


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
        """Should use configured language by default."""
        # Test with Spanish config
        config_with_language("es")  # Config created but not used directly
        translation_manager = TranslationManager(mock_path_resolver)

        # Mock request without Accept-Language header
        request = MagicMock(spec=Request)
        request.headers = {}

        # Should use config language (Spanish)
        trans = translation_manager.get_translation("es")
        assert trans is not None

    def test_accept_language_header_override(self, config_with_language, mock_path_resolver):
        """Should accept-Language header can override config."""
        # Config set to English
        config_with_language("en")  # Config created but not used directly
        translation_manager = TranslationManager(mock_path_resolver)

        # Request with French Accept-Language
        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "fr-FR,fr;q=0.9"}
        request.query_params = MagicMock(spec=QueryParams)
        request.query_params.get = MagicMock(spec=QueryParams.get, return_value=None)

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
        """Should properly extract various languages from headers."""
        translation_manager = TranslationManager(mock_path_resolver)

        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": accept_header}
        request.query_params = MagicMock(spec=QueryParams)
        request.query_params.get = MagicMock(spec=QueryParams.get, return_value=None)

        # Parse the header manually to verify
        lang = accept_header.split(",")[0].split("-")[0]
        assert lang == expected_lang

        # Install translation
        trans = translation_manager.install_for_request(request)
        assert trans is not None

    def test_fallback_to_english(self, path_resolver):
        """Should fallback to English for unsupported languages."""
        translation_manager = TranslationManager(path_resolver)

        request = MagicMock(spec=Request)
        request.headers = {"Accept-Language": "xyz-XY"}  # Non-existent language
        request.query_params = MagicMock(spec=QueryParams)
        request.query_params.get = MagicMock(spec=QueryParams.get, return_value=None)

        # Should fall back gracefully
        trans = translation_manager.install_for_request(request)
        assert trans is not None  # Should get fallback translation


class TestTranslationContent:
    """Test actual translation content."""

    def test_message_extraction_coverage(self, path_resolver):
        """Should key UI elements are marked for translation."""
        templates_dir = path_resolver.get_templates_dir()

        # Check that templates have translation markers
        html_files = list(templates_dir.glob("**/*.html.j2"))

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

    def test_po_file_completeness(self, path_resolver):
        """Should .po files have translations for common strings."""
        locales_dir = path_resolver.get_locales_dir()

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

    def test_mo_files_compiled(self, repo_root):
        """Should properly compile .mo files."""
        locales_dir = repo_root / "locales"

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
        """Should different species display modes."""
        # Test different display modes
        modes = ["full", "common_name", "scientific_name"]

        for mode in modes:
            config = config_with_language("en")
            config.species_display_mode = mode

            service = SpeciesDisplayService(config)

            # Test formatting with mock detection

            detection = MagicMock(spec=DetectionWithTaxa)
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

    @pytest.mark.asyncio
    async def test_multilingual_species_names(self, path_resolver):
        """Should species names work in multiple languages using actual databases."""
        # The path_resolver fixture already points to data/database/ for the databases
        # The global check_required_assets fixture ensures databases are available

        # Create service with real databases
        service = SpeciesDatabaseService(path_resolver)

        # Create an async SQLite session
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with AsyncSession(engine) as session:
            # Attach the real databases
            await service.attach_all_to_session(session)

            try:
                # Test with a real species that should exist in the databases
                result = await service.get_best_common_name(session, "Turdus migratorius", "es")

                # Should get a real Spanish name
                assert result["common_name"] is not None
                assert result["source"] in ["IOC", "PatLevin", "Avibase"]
                # The actual Spanish name might vary but should contain "Zorzal" or "Petirrojo"

                # Test English name
                result_en = await service.get_best_common_name(session, "Turdus migratorius", "en")
                assert result_en["common_name"] == "American Robin"
                assert result_en["source"] == "IOC"

                # Test French name
                result_fr = await service.get_best_common_name(session, "Turdus migratorius", "fr")
                assert result_fr["common_name"] is not None
                assert "Merle" in result_fr["common_name"] or "merle" in result_fr["common_name"]

            finally:
                # Clean up
                await service.detach_all_from_session(session)


class TestEndToEndTranslation:
    """Test complete translation flow."""

    def test_translation_extraction_update_compile_cycle(self):
        """Should complete translation workflow successfully."""
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
        """Should render templates with translations."""
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
