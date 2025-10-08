"""Tests for IOC database builder utility."""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.utils.ioc_database_builder import IocDatabaseBuilder


class TestIocDatabaseBuilder:
    """Test IOC database builder."""

    def test_database_builder_initialization(self, tmp_path):
        """Should initialize with database path."""
        db_path = tmp_path / "test.db"
        builder = IocDatabaseBuilder(db_path=db_path)
        assert builder.db_path == db_path
        assert db_path.parent.exists()

    @patch("birdnetpi.utils.ioc_database_builder.ET.parse", autospec=True)
    def test_populate_from_files_xml_only(self, mock_parse, tmp_path):
        """Should populate database from XML file."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml>test</xml>")
        db_path = tmp_path / "test.db"
        mock_tree = MagicMock(spec=ET.ElementTree)
        mock_root = MagicMock(spec=ET.Element)
        mock_root.get.return_value = "15.1"
        mock_root.findall.return_value = []
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree
        builder = IocDatabaseBuilder(db_path=db_path)
        builder.populate_from_files(xml_file)
        mock_parse.assert_called_once()

    def test_populate_from_files_missing_xml(self, tmp_path):
        """Should raise error when XML file is missing."""
        xml_file = tmp_path / "missing.xml"
        db_path = tmp_path / "test.db"
        builder = IocDatabaseBuilder(db_path=db_path)
        with pytest.raises(FileNotFoundError, match="XML file not found"):
            builder.populate_from_files(xml_file)
