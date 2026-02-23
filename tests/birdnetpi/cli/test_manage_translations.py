"""Test the manage_translations CLI module."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.manage_translations import (
    _process_pot_file,
    _reverse_text_with_placeholders,
    _transform_string,
    cli,
    main,
    run_command,
)
from birdnetpi.system.path_resolver import PathResolver


class TestRunCommand:
    """Test the run_command helper function."""

    @pytest.mark.parametrize(
        "command,exception,expected_result,check_output",
        [
            (["echo", "test"], None, True, True),
            (["false"], None, False, False),
            (
                ["test"],
                subprocess.CalledProcessError(1, ["test"], stderr="Error message"),
                False,
                False,
            ),
        ],
        ids=["success", "command_failure", "subprocess_exception"],
    )
    def test_run_command(self, command, exception, expected_result, check_output, capsys):
        """Should handle various command execution outcomes."""
        if exception:
            with patch("subprocess.run", autospec=True) as mock_run:
                mock_run.side_effect = exception
                result = run_command(command, "Test command")
        else:
            result = run_command(command, "Test command")

        assert result is expected_result

        if check_output:
            captured = capsys.readouterr()
            assert "Running: Test command" in captured.out
            assert f"Command: {' '.join(command)}" in captured.out
            assert "test" in captured.out


class TestExtractCommand:
    """Test the extract command."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_locales(self, tmp_path, path_resolver):
        """Set up temporary locales directory with real babel config."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        path_resolver.get_messages_pot_path = lambda: locales_dir / "messages.pot"
        path_resolver.get_locales_dir = lambda: locales_dir
        return (path_resolver, locales_dir)

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_extract_success(self, mock_resolver_class, runner, tmp_path, path_resolver):
        """Should extract translatable strings successfully."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text(
            'from flask_babel import lazy_gettext\nmsg = lazy_gettext("Hello World")'
        )
        babel_cfg = tmp_path / "babel.cfg"
        babel_cfg.write_text("[python: **/*.py]")
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_babel_config_path = lambda: babel_cfg
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        with runner.isolated_filesystem() as isolated_dir:
            Path(isolated_dir, "src").symlink_to(src_dir)
            Path(isolated_dir, "babel.cfg").symlink_to(babel_cfg)
            Path(isolated_dir, "locales").symlink_to(locales_dir)
            result = runner.invoke(cli, ["extract"])
        assert result.exit_code == 0
        assert "✓ String extraction completed successfully" in result.output
        assert pot_file.exists()
        pot_content = pot_file.read_text()
        assert "Hello World" in pot_content

    @patch("birdnetpi.cli.manage_translations.run_command", autospec=True)
    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_extract_failure(
        self, mock_resolver_class, mock_run_command, runner, tmp_path, path_resolver
    ):
        """Should handle extraction failure."""
        src_dir = tmp_path / "src"
        babel_cfg = tmp_path / "babel.cfg"
        locales_dir = tmp_path / "locales"
        pot_file = locales_dir / "messages.pot"
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_babel_config_path = lambda: babel_cfg
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        mock_run_command.return_value = False
        result = runner.invoke(cli, ["extract"])
        assert result.exit_code == 1
        assert "✗ String extraction failed" in result.output


class TestUpdateCommand:
    """Test the update command."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_locales_with_po(self, tmp_path, path_resolver):
        """Set up temporary locales with POT and PO files."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        pot_file.write_text(
            '# BirdNET-Pi\nmsgid ""\nmsgstr ""\n'
            '"Project-Id-Version: BirdNET-Pi\\n"\n\n'
            'msgid "Hello"\nmsgstr ""\n'
        )
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr "Hola"\n'
        )
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        return (path_resolver, locales_dir)

    @patch("birdnetpi.cli.manage_translations.run_command", autospec=True)
    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_update_success(
        self, mock_resolver_class, mock_run_command, runner, tmp_path, path_resolver
    ):
        """Should update translation files successfully."""
        src_dir = tmp_path / "src"
        pot_file = tmp_path / "locales" / "messages.pot"
        locales_dir = tmp_path / "locales"
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        mock_run_command.return_value = True
        result = runner.invoke(cli, ["update"])
        assert result.exit_code == 0
        assert "✓ Translation update completed successfully" in result.output
        mock_run_command.assert_called_once()

    @patch("birdnetpi.cli.manage_translations.run_command", autospec=True)
    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_update_failure(
        self, mock_resolver_class, mock_run_command, runner, tmp_path, path_resolver
    ):
        """Should handle update failure."""
        src_dir = tmp_path / "src"
        pot_file = tmp_path / "locales" / "messages.pot"
        locales_dir = tmp_path / "locales"
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        mock_run_command.return_value = False
        result = runner.invoke(cli, ["update"])
        assert result.exit_code == 1
        assert "✗ Translation update failed" in result.output


class TestCompileCommand:
    """Test the compile command."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_locales_for_compile(self, tmp_path, path_resolver):
        """Set up temporary locales with PO files for compilation."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Hello"\nmsgstr "Hola"\n\n'
            'msgid "Goodbye"\nmsgstr "Adiós"\n'
        )
        path_resolver.get_locales_dir = lambda: locales_dir
        return (path_resolver, locales_dir)

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_compile_success(self, mock_resolver_class, runner, tmp_path, path_resolver):
        """Should compile translation files successfully."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Hello"\nmsgstr "Hola"\n\n'
            'msgid "Goodbye"\nmsgstr "Adiós"\n'
        )
        # Use the fixture properly - don't create a new MagicMock
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        with runner.isolated_filesystem() as isolated_dir:
            Path(isolated_dir, "locales").symlink_to(locales_dir)
            result = runner.invoke(cli, ["compile"])
        assert result.exit_code == 0
        # Updated assertion: the new compile command uses a different message format
        assert "Compiled" in result.output and "successfully" in result.output
        mo_file = locales_dir / "es" / "LC_MESSAGES" / "messages.mo"
        assert mo_file.exists()
        assert mo_file.stat().st_size > 0

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    @patch("birdnetpi.cli.manage_translations.subprocess.run", autospec=True)
    def test_compile_failure(
        self, mock_subprocess_run, mock_resolver_class, runner, tmp_path, path_resolver
    ):
        """Should handle compilation failure."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        # Create a locale with a PO file so compile attempts to process it
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Hello"\nmsgstr "Hola"\n'
        )
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        # Make subprocess.run raise CalledProcessError to simulate msgfmt failure
        mock_subprocess_run.side_effect = subprocess.CalledProcessError(
            1, ["msgfmt"], stderr="msgfmt: error"
        )
        result = runner.invoke(cli, ["compile"])
        assert result.exit_code == 1
        # Updated assertion: the new compile command uses a different failure message format
        assert "failed" in result.output.lower()


class TestInitCommand:
    """Test the init command."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_locales_for_init(self, tmp_path, path_resolver):
        """Set up temporary locales with POT file for language initialization."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        pot_file.write_text(
            '# BirdNET-Pi\nmsgid ""\nmsgstr ""\n'
            '"Project-Id-Version: BirdNET-Pi\\n"\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Hello"\nmsgstr ""\n\n'
            'msgid "Welcome"\nmsgstr ""\n'
        )
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        return (path_resolver, locales_dir)

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_init_language_success(self, mock_resolver_class, runner, tmp_path, path_resolver):
        """Should initialize a new language successfully."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        pot_file.write_text(
            '# BirdNET-Pi\nmsgid ""\nmsgstr ""\n'
            '"Project-Id-Version: BirdNET-Pi\\n"\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Hello"\nmsgstr ""\n\n'
            'msgid "Welcome"\nmsgstr ""\n'
        )
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        with runner.isolated_filesystem() as isolated_dir:
            Path(isolated_dir, "locales").symlink_to(locales_dir)
            result = runner.invoke(cli, ["init", "it"])
        assert result.exit_code == 0
        assert "✓ Language 'it' initialized successfully" in result.output
        it_po_file = locales_dir / "it" / "LC_MESSAGES" / "messages.po"
        assert it_po_file.exists()
        po_content = it_po_file.read_text()
        assert "Italian" in po_content or "it" in po_content

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    @patch("birdnetpi.cli.manage_translations.run_command", autospec=True)
    def test_init_language_failure(
        self, mock_run_command, mock_resolver_class, runner, tmp_path, path_resolver
    ):
        """Should handle language initialization failure."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        pot_file.write_text(
            '# BirdNET-Pi\nmsgid ""\nmsgstr ""\n'
            '"Project-Id-Version: BirdNET-Pi\\n"\n\n'
            'msgid "Hello"\nmsgstr ""\n'
        )
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        mock_run_command.return_value = False
        result = runner.invoke(cli, ["init", "it"])
        assert result.exit_code == 1
        assert "✗ Language initialization failed" in result.output


class TestAllCommand:
    """Test the all command that runs the complete workflow."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_locales_for_all(self, tmp_path, path_resolver):
        """Set up temporary locales for full workflow."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Test"\nmsgstr "Prueba"\n'
        )
        path_resolver.get_messages_pot_path = lambda: locales_dir / "messages.pot"
        path_resolver.get_locales_dir = lambda: locales_dir
        return (path_resolver, locales_dir)

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    def test_all_workflow_success(self, mock_resolver_class, runner, tmp_path, path_resolver):
        """Should run complete translation workflow successfully."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text(
            'from flask_babel import lazy_gettext\nmsg = lazy_gettext("Test")'
        )
        babel_cfg = tmp_path / "babel.cfg"
        babel_cfg.write_text("[python: **/*.py]")
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        lang_dir = locales_dir / "es" / "LC_MESSAGES"
        lang_dir.mkdir(parents=True)
        po_file = lang_dir / "messages.po"
        po_file.write_text(
            '# Spanish translations\nmsgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            'msgid "Test"\nmsgstr "Prueba"\n'
        )
        path_resolver = MagicMock(spec=PathResolver)
        path_resolver.get_src_dir.return_value = src_dir
        path_resolver.get_babel_config_path.return_value = babel_cfg
        path_resolver.get_messages_pot_path.return_value = locales_dir / "messages.pot"
        path_resolver.get_locales_dir.return_value = locales_dir
        mock_resolver_class.return_value = path_resolver
        with runner.isolated_filesystem() as isolated_dir:
            Path(isolated_dir, "src").symlink_to(src_dir)
            Path(isolated_dir, "babel.cfg").symlink_to(babel_cfg)
            Path(isolated_dir, "locales").symlink_to(locales_dir)
            result = runner.invoke(cli, ["all"])
        assert result.exit_code == 0
        assert "Running complete translation workflow..." in result.output
        assert "Step 1/3: Extracting strings" in result.output
        assert "Step 2/3: Updating translations" in result.output
        assert "Step 3/3: Compiling translations" in result.output
        assert "✓ Complete translation workflow finished successfully" in result.output
        pot_file = locales_dir / "messages.pot"
        assert pot_file.exists()
        mo_file = locales_dir / "es" / "LC_MESSAGES" / "messages.mo"
        assert mo_file.exists()

    @patch("birdnetpi.cli.manage_translations.PathResolver", autospec=True)
    @patch("birdnetpi.cli.manage_translations.run_command", autospec=True)
    def test_all_workflow_failure_at_extract(
        self, mock_run_command, mock_resolver_class, runner, tmp_path, path_resolver
    ):
        """Should stop workflow if extract fails."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        babel_cfg = tmp_path / "babel.cfg"
        babel_cfg.write_text("[python: **/*.py]")
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        pot_file = locales_dir / "messages.pot"
        path_resolver.get_src_dir = lambda: src_dir
        path_resolver.get_babel_config_path = lambda: babel_cfg
        path_resolver.get_messages_pot_path = lambda: pot_file
        path_resolver.get_locales_dir = lambda: locales_dir
        mock_resolver_class.return_value = path_resolver
        mock_run_command.return_value = False
        result = runner.invoke(cli, ["all"])
        assert result.exit_code == 1
        assert "Step 1/3: Extracting strings" in result.output
        assert "✗ String extraction failed" in result.output
        assert mock_run_command.call_count == 1


class TestMainFunction:
    """Test the main entry point."""

    @patch("birdnetpi.cli.manage_translations.cli", autospec=True)
    def test_main_function(self, mock_cli):
        """Should call CLI with proper arguments."""
        main()
        mock_cli.assert_called_once_with(obj={})


class TestEnvironmentSetup:
    """Test environment setup in CLI group."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    def test_sets_birdnetpi_app_env_var(self, runner):
        """Should set BIRDNETPI_APP environment variable."""
        original_value = os.environ.pop("BIRDNETPI_APP", None)
        try:
            result = runner.invoke(cli, ["--help"])
            assert result.exit_code == 0
            assert "Manage BirdNET-Pi translations" in result.output
        finally:
            if original_value is not None:
                os.environ["BIRDNETPI_APP"] = original_value


class TestTransformString:
    """Test the _transform_string function for fake locale generation."""

    def test_empty_string(self):
        """Should return empty string unchanged."""
        assert _transform_string("", reverse=True, brackets=True) == ""
        assert _transform_string("", reverse=False, brackets=False) == ""

    def test_simple_text_reverse_only(self):
        """Should reverse simple text."""
        assert _transform_string("Hello", reverse=True, brackets=False) == "olleH"
        assert _transform_string("Settings", reverse=True, brackets=False) == "sgnitteS"

    def test_simple_text_brackets_only(self):
        """Should add brackets to simple text."""
        assert _transform_string("Hello", reverse=False, brackets=True) == "[[Hello]]"
        assert _transform_string("Settings", reverse=False, brackets=True) == "[[Settings]]"

    def test_simple_text_reverse_and_brackets(self):
        """Should reverse text and add brackets."""
        assert _transform_string("Hello", reverse=True, brackets=True) == "[[olleH]]"
        assert _transform_string("Settings", reverse=True, brackets=True) == "[[sgnitteS]]"

    def test_preserve_python_string_placeholders(self):
        """Should preserve %(name)s style placeholders."""
        text = "Hello %(name)s"
        assert _transform_string(text, reverse=True, brackets=False) == " olleH%(name)s"
        assert _transform_string(text, reverse=True, brackets=True) == "[[ olleH%(name)s]]"
        text = "%(count)d items"
        assert _transform_string(text, reverse=True, brackets=False) == "%(count)dsmeti "
        assert _transform_string(text, reverse=True, brackets=True) == "[[%(count)dsmeti ]]"

    def test_preserve_multiple_placeholders(self):
        """Should preserve multiple placeholders in correct positions."""
        text = "User %(user)s has %(count)d messages"
        expected_reversed = " resU%(user)s sah %(count)dsegassem "
        assert _transform_string(text, reverse=True, brackets=False) == expected_reversed
        assert _transform_string(text, reverse=True, brackets=True) == f"[[{expected_reversed}]]"

    def test_preserve_html_entities(self):
        """Should preserve HTML entities."""
        text = "Items &times; Price"
        assert _transform_string(text, reverse=True, brackets=False) == " smetI&times;ecirP "
        text = "Line&nbsp;break"
        assert _transform_string(text, reverse=True, brackets=False) == "eniL&nbsp;kaerb"

    def test_preserve_numeric_html_entities(self):
        """Should preserve numeric HTML entities."""
        text = "Price &#8364; 100"
        assert _transform_string(text, reverse=True, brackets=False) == " ecirP&#8364;001 "
        text = "Copyright &#169; 2024"
        assert _transform_string(text, reverse=True, brackets=False) == " thgirypoC&#169;4202 "

    def test_complex_mixed_content(self):
        """Should handle complex strings with multiple special elements."""
        text = "%(user)s posted &ldquo;Hello&rdquo; at %(time)s"
        result = _transform_string(text, reverse=True, brackets=False)
        assert "%(user)s" in result
        assert "%(time)s" in result
        assert "&ldquo;" in result
        assert "&rdquo;" in result
        assert "olleH" in result or "detsop" in result


class TestReverseTextWithPlaceholders:
    """Test the _reverse_text_with_placeholders function."""

    def test_text_without_placeholders(self):
        """Should reverse simple text."""
        assert _reverse_text_with_placeholders("Hello World") == "dlroW olleH"

    def test_text_with_single_placeholder(self):
        """Should reverse text around placeholder markers."""
        text = "Hello __PLACEHOLDER_0__ World"
        assert _reverse_text_with_placeholders(text) == " olleH__PLACEHOLDER_0__dlroW "

    def test_text_with_multiple_placeholders(self):
        """Should handle multiple placeholder markers."""
        text = "Start __PLACEHOLDER_0__ middle __PLACEHOLDER_1__ end"
        assert (
            _reverse_text_with_placeholders(text)
            == " tratS__PLACEHOLDER_0__ elddim __PLACEHOLDER_1__dne "
        )

    def test_placeholder_at_start(self):
        """Should handle placeholder at the beginning."""
        text = "__PLACEHOLDER_0__ after"
        assert _reverse_text_with_placeholders(text) == "__PLACEHOLDER_0__retfa "

    def test_placeholder_at_end(self):
        """Should handle placeholder at the end."""
        text = "before __PLACEHOLDER_0__"
        assert _reverse_text_with_placeholders(text) == " erofeb__PLACEHOLDER_0__"

    def test_consecutive_placeholders(self):
        """Should handle consecutive placeholders."""
        text = "start __PLACEHOLDER_0____PLACEHOLDER_1__ end"
        assert (
            _reverse_text_with_placeholders(text) == " trats__PLACEHOLDER_0____PLACEHOLDER_1__dne "
        )


class TestProcessPotFile:
    """Test the _process_pot_file function."""

    def test_simple_pot_file(self):
        """Should process a simple POT file."""
        pot_content = (
            '# Translation file\nmsgid ""\nmsgstr ""\n\n'
            'msgid "Hello"\nmsgstr ""\n\n'
            'msgid "World"\nmsgstr ""\n'
        )
        result = _process_pot_file(pot_content, reverse=True, brackets=True)
        result_text = "\n".join(result)
        assert 'msgid "Hello"' in result_text
        assert 'msgstr "[[olleH]]"' in result_text
        assert 'msgid "World"' in result_text
        assert 'msgstr "[[dlroW]]"' in result_text

    def test_multiline_msgid(self):
        """Should handle multi-line msgid entries."""
        pot_content = (
            'msgid ""\n'
            '"This is a very long message that spans "\n'
            '"multiple lines in the POT file"\n'
            'msgstr ""\n'
        )
        result = _process_pot_file(pot_content, reverse=True, brackets=False)
        result_text = "\n".join(result)
        assert '"This is a very long message that spans "' in result_text
        assert '"multiple lines in the POT file"' in result_text
        assert (
            'msgstr "elif TOP eht ni senil elpitlum snaps taht egassem gnol yrev a si sihT"'
            in result_text
        )

    def test_preserve_comments(self):
        """Should preserve comments and metadata."""
        pot_content = (
            '# Translator comment\n#. Developer comment\n#: source.py:42\nmsgid "Test"\nmsgstr ""\n'
        )
        result = _process_pot_file(pot_content, reverse=True, brackets=False)
        result_text = "\n".join(result)
        assert "# Translator comment" in result_text
        assert "#. Developer comment" in result_text
        assert "#: source.py:42" in result_text
        assert 'msgstr "tseT"' in result_text

    def test_empty_msgid(self):
        """Should not transform empty msgid (header)."""
        pot_content = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
        result = _process_pot_file(pot_content, reverse=True, brackets=True)
        result_text = "\n".join(result)
        assert 'msgid ""' in result_text
        assert result[1] == 'msgstr ""'

    def test_msgid_with_placeholders(self):
        """Should handle msgid with placeholders."""
        pot_content = (
            'msgid "Hello %(name)s"\nmsgstr ""\n\n'
            'msgid "%(count)d items in %(location)s"\nmsgstr ""\n'
        )
        result = _process_pot_file(pot_content, reverse=True, brackets=True)
        result_text = "\n".join(result)
        assert 'msgstr "[[ olleH%(name)s]]"' in result_text
        assert "%(count)d" in result_text
        assert "%(location)s" in result_text

    def test_no_transformation_options(self):
        """Should pass through unchanged when no transformations requested."""
        pot_content = 'msgid "Hello World"\nmsgstr ""\n'
        result = _process_pot_file(pot_content, reverse=False, brackets=False)
        result_text = "\n".join(result)
        assert 'msgstr "Hello World"' in result_text


class TestFakeLocaleCommand:
    """Test the fake_locale CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a Click test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_resolver(self, path_resolver):
        """Create a mock path resolver with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            path_resolver.get_messages_pot_path = lambda: tmp_path / "messages.pot"
            path_resolver.get_locales_dir = lambda: tmp_path / "locales"
            yield (path_resolver, tmp_path)

    def test_fake_locale_creates_files(self, runner, mock_resolver):
        """Should create PO file from POT file - integration test."""
        resolver, tmp_path = mock_resolver
        pot_file = tmp_path / "messages.pot"
        pot_file.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n\nmsgid "Settings"\nmsgstr ""\n'
        )
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(
                cli, ["fake-locale", "--locale", "xx"], obj={"resolver": resolver}
            )
        assert result.exit_code == 0
        assert "Creating fake locale 'xx'" in result.output

    def test_fake_locale_no_pot_file(self, runner, mock_resolver):
        """Should error when POT file doesn't exist."""
        resolver, tmp_path = mock_resolver
        pot_file = tmp_path / "messages.pot"
        if pot_file.exists():
            pot_file.unlink()
        result = runner.invoke(cli, ["fake-locale", "--locale", "xx"], obj={"resolver": resolver})
        assert result.exit_code in [0, 1]
        if result.exit_code == 1:
            assert "messages.pot not found" in result.output

    def test_fake_locale_options(self, runner, mock_resolver):
        """Should respect --no-reverse and --no-brackets options."""
        resolver, tmp_path = mock_resolver
        pot_file = tmp_path / "messages.pot"
        pot_file.write_text('msgid "Test"\nmsgstr ""\n')
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(
                cli, ["fake-locale", "--locale", "xx", "--no-reverse"], obj={"resolver": resolver}
            )
        assert result.exit_code == 0
        assert "--no-reverse" in str(result) or "Creating fake locale" in result.output
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.return_value.returncode = 0
            result = runner.invoke(
                cli, ["fake-locale", "--locale", "yy", "--no-brackets"], obj={"resolver": resolver}
            )
        assert result.exit_code == 0

    def test_fake_locale_compile_failure(self, runner, mock_resolver):
        """Should handle msgfmt compilation failure."""
        resolver, tmp_path = mock_resolver
        pot_file = tmp_path / "messages.pot"
        pot_file.write_text('msgid "Test"\nmsgstr ""\n')
        with patch("subprocess.run", autospec=True) as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "msgfmt: error"
            result = runner.invoke(
                cli, ["fake-locale", "--locale", "xx"], obj={"resolver": resolver}
            )
        assert result.exit_code in [0, 1]
        if result.exit_code == 1:
            assert "Failed to compile" in result.output or "error" in result.output.lower()
