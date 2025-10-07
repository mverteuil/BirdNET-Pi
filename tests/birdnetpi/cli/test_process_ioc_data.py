"""Tests for IOC database builder CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.process_ioc_data import cli
from birdnetpi.utils.ioc_database_builder import IocDatabaseBuilder


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


class TestIOCDataProcessor:
    """Test IOC database builder commands."""

    @patch("birdnetpi.cli.process_ioc_data.IocDatabaseBuilder", autospec=True)
    def test_build_command_with_xml_only(self, mock_builder_class, runner, tmp_path):
        """Should build database from XML file only."""
        # Setup mocks
        mock_builder = MagicMock(spec=IocDatabaseBuilder)
        mock_builder_class.return_value = mock_builder

        # Create test files
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        db_file = tmp_path / "output.db"

        result = runner.invoke(
            cli,
            [
                "build",
                "--xml-file",
                str(xml_file),
                "--db-file",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        assert "Building IOC database..." in result.output
        assert f"XML file: {xml_file}" in result.output
        assert f"Database: {db_file}" in result.output
        assert "✓ Database built successfully" in result.output

        mock_builder_class.assert_called_once_with(db_path=db_file)
        mock_builder.populate_from_files.assert_called_once_with(xml_file, None)

    @patch("birdnetpi.cli.process_ioc_data.IocDatabaseBuilder", autospec=True)
    def test_build_command_with_xml_and_xlsx(self, mock_builder_class, runner, tmp_path):
        """Should build database from XML and XLSX files."""
        # Setup mocks
        mock_builder = MagicMock(spec=IocDatabaseBuilder)
        mock_builder_class.return_value = mock_builder

        # Create test files
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.write_bytes(b"test")
        db_file = tmp_path / "output.db"

        result = runner.invoke(
            cli,
            [
                "build",
                "--xml-file",
                str(xml_file),
                "--xlsx-file",
                str(xlsx_file),
                "--db-file",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        assert "Building IOC database..." in result.output
        assert f"XML file: {xml_file}" in result.output
        assert f"XLSX file: {xlsx_file}" in result.output
        assert f"Database: {db_file}" in result.output
        assert "✓ Database built successfully" in result.output

        mock_builder_class.assert_called_once_with(db_path=db_file)
        mock_builder.populate_from_files.assert_called_once_with(xml_file, xlsx_file)

    @patch("birdnetpi.cli.process_ioc_data.IocDatabaseBuilder", autospec=True)
    def test_build_command_file_not_found(self, mock_builder_class, runner, tmp_path):
        """Should handle file not found error gracefully."""
        # Setup mocks
        mock_builder = MagicMock(spec=IocDatabaseBuilder)
        mock_builder.populate_from_files.side_effect = FileNotFoundError("XML file not found")
        mock_builder_class.return_value = mock_builder

        # Create test XML file (to pass Click's validation)
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        db_file = tmp_path / "output.db"

        result = runner.invoke(
            cli,
            [
                "build",
                "--xml-file",
                str(xml_file),
                "--db-file",
                str(db_file),
            ],
        )

        assert result.exit_code == 1
        assert "✗ File not found: XML file not found" in result.output

    @patch("birdnetpi.cli.process_ioc_data.IocDatabaseBuilder", autospec=True)
    def test_build_command_general_error(self, mock_builder_class, runner, tmp_path):
        """Should handle general errors gracefully."""
        # Setup mocks
        mock_builder = MagicMock(spec=IocDatabaseBuilder)
        mock_builder.populate_from_files.side_effect = Exception("Database error")
        mock_builder_class.return_value = mock_builder

        # Create test files
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        db_file = tmp_path / "output.db"

        result = runner.invoke(
            cli,
            [
                "build",
                "--xml-file",
                str(xml_file),
                "--db-file",
                str(db_file),
            ],
        )

        assert result.exit_code == 1
        assert "✗ Error building database: Database error" in result.output

    def test_main_help(self, runner):
        """Should show help text."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "IOC World Bird Names database builder" in result.output
        assert "build" in result.output

    def test_build_help(self, runner):
        """Should show build command help."""
        result = runner.invoke(cli, ["build", "--help"])

        assert result.exit_code == 0
        assert "Build IOC database from XML and optionally XLSX files" in result.output
        assert "--xml-file" in result.output
        assert "--xlsx-file" in result.output
        assert "--db-file" in result.output
