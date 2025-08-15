"""Tests for IOC data processor CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.ioc_data_processor import cli


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_ioc_reference_service():
    """Create a mock IOCReferenceService."""
    mock_service = MagicMock()
    mock_service.get_ioc_version.return_value = "15.1"
    mock_service.get_species_count.return_value = 10832
    mock_service.get_available_languages.return_value = {"en", "es", "fr", "de"}
    mock_service._species_data = {
        "Turdus migratorius": MagicMock(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            authority="Linnaeus, 1766",
        )
    }
    mock_service._translations = {
        "Turdus migratorius": {
            "es": "Mirlo primavera",
            "fr": "Merle d'Amérique",
            "de": "Wanderdrossel",
        }
    }
    return mock_service


class TestIOCDataProcessor:
    """Test IOC data processor commands."""

    @patch("birdnetpi.cli.ioc_data_processor.IOCDatabaseService")
    @patch("birdnetpi.cli.ioc_data_processor.IOCReferenceService")
    def test_process_command(
        self, mock_reference_service_class, mock_database_service_class, runner, tmp_path
    ):
        """Should process IOC files into JSON format."""
        # Setup mocks
        mock_service = MagicMock()
        mock_service.get_species_count.return_value = 10832
        mock_service.get_available_languages.return_value = {"en", "es", "fr"}
        mock_reference_service_class.return_value = mock_service

        # Create test files
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.write_bytes(b"test")
        output_file = tmp_path / "output.json"

        result = runner.invoke(
            cli,
            [
                "process",
                "--xml-file",
                str(xml_file),
                "--xlsx-file",
                str(xlsx_file),
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert "Processing IOC data files" in result.output
        assert "✓ JSON data saved successfully" in result.output
        assert "Species count: 10832" in result.output

        mock_service.process_ioc_files.assert_called_once_with(str(xml_file), str(xlsx_file))
        mock_service.save_to_json.assert_called_once()

    @patch("birdnetpi.cli.ioc_data_processor.IOCReferenceService")
    def test_info_command(
        self, mock_reference_service_class, mock_ioc_reference_service, runner, tmp_path
    ):
        """Should show information about IOC JSON file."""
        mock_reference_service_class.return_value = mock_ioc_reference_service

        # Create test JSON file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        result = runner.invoke(cli, ["info", "--json-file", str(json_file)])

        assert result.exit_code == 0
        assert "IOC Data Information:" in result.output
        assert "IOC Version: 15.1" in result.output
        assert "Species count: 10832" in result.output
        assert "Available languages: 4" in result.output

    @patch("birdnetpi.cli.ioc_data_processor.IOCReferenceService")
    def test_lookup_command_found(
        self, mock_reference_service_class, mock_ioc_reference_service, runner, tmp_path
    ):
        """Should lookup species successfully."""
        mock_reference_service_class.return_value = mock_ioc_reference_service

        # Setup mock to return species info
        species_info = MagicMock(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            authority="Linnaeus, 1766",
        )
        mock_ioc_reference_service.get_species_info.return_value = species_info
        mock_ioc_reference_service.get_translated_common_name.return_value = "Mirlo primavera"

        # Create test JSON file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        result = runner.invoke(
            cli,
            [
                "lookup",
                "--json-file",
                str(json_file),
                "--species",
                "Turdus migratorius",
                "--language",
                "es",
            ],
        )

        assert result.exit_code == 0
        assert "Species found:" in result.output
        assert "Scientific name: Turdus migratorius" in result.output
        assert "English name: American Robin" in result.output
        assert "ES name: Mirlo primavera" in result.output

    @patch("birdnetpi.cli.ioc_data_processor.IOCReferenceService")
    def test_lookup_command_not_found(
        self, mock_reference_service_class, mock_ioc_reference_service, runner, tmp_path
    ):
        """Should handle species not found."""
        mock_reference_service_class.return_value = mock_ioc_reference_service
        mock_ioc_reference_service.get_species_info.return_value = None

        # Create test JSON file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        result = runner.invoke(
            cli,
            ["lookup", "--json-file", str(json_file), "--species", "Unknown species"],
        )

        assert result.exit_code == 0
        assert "Species not found: Unknown species" in result.output
        assert "Searching for similar names" in result.output

    def test_main_help(self, runner):
        """Should show help text."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "IOC World Bird Names data processor" in result.output
        assert "process" in result.output
        assert "info" in result.output
        assert "lookup" in result.output
