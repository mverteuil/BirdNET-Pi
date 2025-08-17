"""Tests for IOC database builder utility."""

from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.database.ioc.ioc_database_builder import IocDatabaseBuilder


class TestIocDatabaseBuilder:
    """Test IOC database builder."""

    def test_database_builder_initialization(self, tmp_path):
        """Should initialize with database path."""
        db_path = tmp_path / "test.db"
        builder = IocDatabaseBuilder(db_path=db_path)
        assert builder.db_path == db_path
        assert db_path.parent.exists()

    @patch("birdnetpi.database.ioc.ioc_database_builder.ET.parse")
    def test_populate_from_files_xml_only(self, mock_parse, tmp_path):
        """Should populate database from XML file."""
        # Create test files
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        db_path = tmp_path / "test.db"

        # Mock XML parsing
        mock_tree = MagicMock()
        mock_root = MagicMock()
        mock_root.get.return_value = "15.1"
        mock_root.findall.return_value = []
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        # Create builder and populate
        builder = IocDatabaseBuilder(db_path=db_path)
        builder.populate_from_files(xml_file)

        # Verify XML was parsed
        mock_parse.assert_called_once()

    def test_populate_from_files_missing_xml(self, tmp_path):
        """Should raise error when XML file is missing."""
        xml_file = tmp_path / "missing.xml"
        db_path = tmp_path / "test.db"

        builder = IocDatabaseBuilder(db_path=db_path)

        with pytest.raises(FileNotFoundError, match="XML file not found"):
            builder.populate_from_files(xml_file)
