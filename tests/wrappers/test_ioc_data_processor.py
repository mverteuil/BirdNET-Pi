"""Tests for IOC data processor wrapper."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.wrappers.ioc_data_processor import (
    lookup_species,
    main,
    process_ioc_files,
    show_ioc_info,
)


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
        "Turdus migratorius": {"es": "Petirrojo Americano", "fr": "Merle d'Amérique"}
    }
    return mock_service


@pytest.fixture
def mock_ioc_database_service():
    """Create a mock IOCDatabaseService."""
    mock_service = MagicMock()
    mock_service.get_database_size.return_value = 5242880  # 5MB
    return mock_service


class TestProcessIOCFiles:
    """Test process_ioc_files function."""

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCDatabaseService")
    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_process_ioc_files_missing_xml(
        self, mock_exit, mock_service_class, mock_db_class, tmp_path
    ):
        """Should exit when XML file is missing."""
        xml_file = tmp_path / "missing.xml"
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json"

        process_ioc_files(xml_file, xlsx_file, output_file)

        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCDatabaseService")
    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_process_ioc_files_missing_xlsx(
        self, mock_exit, mock_service_class, mock_db_class, tmp_path
    ):
        """Should exit when XLSX file is missing."""
        xml_file = tmp_path / "test.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "missing.xlsx"
        output_file = tmp_path / "output.json"

        process_ioc_files(xml_file, xlsx_file, output_file)

        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCDatabaseService")
    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_process_ioc_files_success(
        self, mock_service_class, mock_db_class, mock_ioc_reference_service, tmp_path, capsys
    ):
        """Should process IOC files successfully."""
        # Setup files
        xml_file = tmp_path / "test.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json"

        # Setup mock service
        mock_service_class.return_value = mock_ioc_reference_service

        # Create a fake JSON file for size calculation
        output_file.write_text('{"test": "data"}')

        process_ioc_files(xml_file, xlsx_file, output_file)

        # Verify service was called correctly
        mock_ioc_reference_service.load_ioc_data.assert_called_once_with(
            xml_file=xml_file, xlsx_file=xlsx_file
        )
        mock_ioc_reference_service.export_json.assert_called_once_with(
            output_file, include_translations=True, compress=False
        )

        # Check output
        captured = capsys.readouterr()
        assert "Processing complete!" in captured.out
        assert "IOC Version: 15.1" in captured.out
        assert "Species count: 10832" in captured.out

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCDatabaseService")
    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_process_ioc_files_with_database(
        self,
        mock_service_class,
        mock_db_class,
        mock_ioc_reference_service,
        mock_ioc_database_service,
        tmp_path,
        capsys,
    ):
        """Should process IOC files and create database."""
        # Setup files
        xml_file = tmp_path / "test.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json"
        db_file = tmp_path / "test.db"

        # Setup mocks
        mock_service_class.return_value = mock_ioc_reference_service
        mock_db_class.return_value = mock_ioc_database_service

        # Create fake files for size calculation
        output_file.write_text('{"test": "data"}')  # 15 bytes

        process_ioc_files(xml_file, xlsx_file, output_file, compress=False, db_file=db_file)

        # Verify database service was called
        mock_db_class.assert_called_once_with(str(db_file))
        mock_ioc_database_service.populate_from_ioc_service.assert_called_once_with(
            mock_ioc_reference_service
        )

        # Check output includes database info
        captured = capsys.readouterr()
        assert "Creating SQLite database..." in captured.out
        assert "SQLite output:" in captured.out

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_process_ioc_files_service_error(self, mock_exit, mock_service_class, tmp_path):
        """Should handle service errors gracefully."""
        # Setup files
        xml_file = tmp_path / "test.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json"

        # Setup mock to raise exception
        mock_service = MagicMock()
        mock_service.load_ioc_data.side_effect = Exception("Processing error")
        mock_service_class.return_value = mock_service

        process_ioc_files(xml_file, xlsx_file, output_file)

        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_process_ioc_files_with_compression(
        self, mock_service_class, mock_ioc_reference_service, tmp_path
    ):
        """Should process files with compression enabled."""
        # Setup files
        xml_file = tmp_path / "test.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json.gz"

        mock_service_class.return_value = mock_ioc_reference_service
        output_file.write_bytes(b"compressed data")

        process_ioc_files(xml_file, xlsx_file, output_file, compress=True)

        # Verify compression was enabled
        mock_ioc_reference_service.export_json.assert_called_once_with(
            output_file, include_translations=True, compress=True
        )


class TestShowIOCInfo:
    """Test show_ioc_info function."""

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_show_ioc_info_missing_file(self, mock_exit, mock_service_class, tmp_path):
        """Should exit when JSON file is missing."""
        json_file = tmp_path / "missing.json"

        show_ioc_info(json_file)

        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_show_ioc_info_success(
        self, mock_service_class, mock_ioc_reference_service, tmp_path, capsys
    ):
        """Should show IOC info successfully."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')  # 16 bytes

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service

        show_ioc_info(json_file)

        # Verify service was called correctly
        mock_ioc_reference_service.load_from_json.assert_called_once_with(json_file)

        # Check output
        captured = capsys.readouterr()
        assert "IOC Data Information:" in captured.out
        assert "Size: 16 bytes" in captured.out
        assert "IOC Version: 15.1" in captured.out
        assert "Species count: 10832" in captured.out
        assert "Available language codes:" in captured.out
        assert "Sample species (first 5):" in captured.out

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_show_ioc_info_service_error(self, mock_exit, mock_service_class, tmp_path):
        """Should handle service errors gracefully."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        # Setup mock to raise exception
        mock_service = MagicMock()
        mock_service.load_from_json.side_effect = Exception("Load error")
        mock_service_class.return_value = mock_service

        show_ioc_info(json_file)

        mock_exit.assert_called_with(1)


class TestLookupSpecies:
    """Test lookup_species function."""

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_lookup_missing_file(self, mock_exit, mock_service_class, tmp_path):
        """Should exit when JSON file is missing."""
        json_file = tmp_path / "missing.json"

        lookup_species(json_file, "Turdus migratorius", "en")

        mock_exit.assert_called_with(1)

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_lookup_species_found(
        self, mock_service_class, mock_ioc_reference_service, tmp_path, capsys
    ):
        """Should lookup species successfully."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service

        # Mock species info
        mock_species = MagicMock()
        mock_species.scientific_name = "Turdus migratorius"
        mock_species.english_name = "American Robin"
        mock_species.order = "Passeriformes"
        mock_species.family = "Turdidae"
        mock_species.authority = "Linnaeus, 1766"

        mock_ioc_reference_service.get_species_info.return_value = mock_species
        mock_ioc_reference_service.get_translated_common_name.return_value = "Petirrojo Americano"

        lookup_species(json_file, "Turdus migratorius", "es")

        # Verify service calls
        mock_ioc_reference_service.get_species_info.assert_called_once_with("Turdus migratorius")
        mock_ioc_reference_service.get_translated_common_name.assert_called_once_with(
            "Turdus migratorius", "es"
        )

        # Check output
        captured = capsys.readouterr()
        assert "Species found:" in captured.out
        assert "Scientific name: Turdus migratorius" in captured.out
        assert "English name: American Robin" in captured.out
        assert "ES name: Petirrojo Americano" in captured.out

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_lookup_species_not_found(
        self, mock_service_class, mock_ioc_reference_service, tmp_path, capsys
    ):
        """Should handle species not found."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service
        mock_ioc_reference_service.get_species_info.return_value = None
        mock_ioc_reference_service._species_data = {
            "Turdus migratorius": None,
            "Turdus philomelos": None,
        }

        lookup_species(json_file, "Nonexistent species", "en")

        # Check output
        captured = capsys.readouterr()
        assert "Species not found: Nonexistent species" in captured.out
        assert "Searching for similar names..." in captured.out

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_lookup_english_language(
        self, mock_service_class, mock_ioc_reference_service, tmp_path
    ):
        """Should handle English language lookup without translation."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service

        mock_species = MagicMock()
        mock_species.scientific_name = "Turdus migratorius"
        mock_species.english_name = "American Robin"
        mock_ioc_reference_service.get_species_info.return_value = mock_species

        lookup_species(json_file, "Turdus migratorius", "en")

        # Should not call translation method for English
        mock_ioc_reference_service.get_translated_common_name.assert_not_called()

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_lookup_service_error(self, mock_exit, mock_service_class, tmp_path):
        """Should handle service errors gracefully."""
        # Setup file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        # Setup mock to raise exception
        mock_service = MagicMock()
        mock_service.load_from_json.side_effect = Exception("Load error")
        mock_service_class.return_value = mock_service

        lookup_species(json_file, "Turdus migratorius", "en")

        mock_exit.assert_called_with(1)


class TestMain:
    """Test main function and argument parsing."""

    @patch("birdnetpi.wrappers.ioc_data_processor.process_ioc_files")
    def test_main_process_command(self, mock_process):
        """Should parse process command correctly."""
        test_args = [
            "ioc-processor",
            "process",
            "--xml-file",
            "test.xml",
            "--xlsx-file",
            "test.xlsx",
            "--output",
            "output.json",
            "--compress",
            "--db-file",
            "test.db",
        ]

        with patch.object(sys, "argv", test_args):
            main()

        mock_process.assert_called_once()
        args = mock_process.call_args[0]
        assert str(args[0]) == "test.xml"  # xml_file
        assert str(args[1]) == "test.xlsx"  # xlsx_file
        assert str(args[2]) == "output.json"  # output_file
        assert args[3] is True  # compress
        assert str(args[4]) == "test.db"  # db_file

    @patch("birdnetpi.wrappers.ioc_data_processor.show_ioc_info")
    def test_main_info_command(self, mock_info):
        """Should parse info command correctly."""
        test_args = ["ioc-processor", "info", "--json-file", "test.json"]

        with patch.object(sys, "argv", test_args):
            main()

        mock_info.assert_called_once()
        args = mock_info.call_args[0]
        assert str(args[0]) == "test.json"

    @patch("birdnetpi.wrappers.ioc_data_processor.lookup_species")
    def test_main_lookup_command(self, mock_lookup):
        """Should parse lookup command correctly."""
        test_args = [
            "ioc-processor",
            "lookup",
            "--json-file",
            "test.json",
            "--species",
            "Turdus migratorius",
            "--language",
            "es",
        ]

        with patch.object(sys, "argv", test_args):
            main()

        mock_lookup.assert_called_once()
        args = mock_lookup.call_args[0]
        assert str(args[0]) == "test.json"
        assert args[1] == "Turdus migratorius"
        assert args[2] == "es"

    @patch("birdnetpi.wrappers.ioc_data_processor.sys.exit")
    def test_main_no_command(self, mock_exit, capsys):
        """Should exit when no command provided."""
        test_args = ["ioc-processor"]

        with patch.object(sys, "argv", test_args):
            main()

        mock_exit.assert_called_with(1)

    def test_main_argument_parsing_structure(self):
        """Should have proper argument structure."""
        test_cases = [
            [
                "process",
                "--xml-file",
                "test.xml",
                "--xlsx-file",
                "test.xlsx",
                "--output",
                "out.json",
            ],
            [
                "process",
                "--xml-file",
                "test.xml",
                "--xlsx-file",
                "test.xlsx",
                "--output",
                "out.json",
                "--compress",
            ],
            ["info", "--json-file", "test.json"],
            ["lookup", "--json-file", "test.json", "--species", "Turdus migratorius"],
            [
                "lookup",
                "--json-file",
                "test.json",
                "--species",
                "Turdus migratorius",
                "--language",
                "fr",
            ],
        ]

        for args in test_cases:
            with (
                patch("birdnetpi.wrappers.ioc_data_processor.process_ioc_files"),
                patch("birdnetpi.wrappers.ioc_data_processor.show_ioc_info"),
                patch("birdnetpi.wrappers.ioc_data_processor.lookup_species"),
            ):
                with patch.object(sys, "argv", ["ioc-processor"] + args):
                    try:
                        main()
                    except SystemExit:
                        pass  # argparse calls sys.exit for some cases, that's fine


class TestIntegration:
    """Integration tests for IOC data processor."""

    @patch("birdnetpi.wrappers.ioc_data_processor.IOCReferenceService")
    def test_complete_processing_workflow(
        self, mock_service_class, mock_ioc_reference_service, tmp_path
    ):
        """Should complete full processing workflow."""
        # Setup files
        xml_file = tmp_path / "ioc.xml"
        xml_file.touch()
        xlsx_file = tmp_path / "ioc.xlsx"
        xlsx_file.touch()
        output_file = tmp_path / "output.json"

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service
        output_file.write_text('{"version": "15.1"}')

        process_ioc_files(xml_file, xlsx_file, output_file)

        # Verify complete workflow
        mock_service_class.assert_called_once_with(data_dir=xml_file.parent)
        mock_ioc_reference_service.load_ioc_data.assert_called_once_with(
            xml_file=xml_file, xlsx_file=xlsx_file
        )
        mock_ioc_reference_service.export_json.assert_called_once_with(
            output_file, include_translations=True, compress=False
        )

    def test_argument_validation_edge_cases(self):
        """Should handle argument validation edge cases."""
        # Test required arguments
        with patch.object(sys, "argv", ["ioc-processor", "process"]):
            with pytest.raises(SystemExit):
                main()

        # Test invalid command
        with patch.object(sys, "argv", ["ioc-processor", "invalid-command"]):
            with patch("birdnetpi.wrappers.ioc_data_processor.sys.exit") as mock_exit:
                main()
                mock_exit.assert_called_with(1)
