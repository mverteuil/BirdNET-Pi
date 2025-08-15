"""Tests for IOC database builder utility."""

import gzip
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from birdnetpi.utils.ioc_database_builder import (
    IOCDatabaseBuilder,
    IOCSpeciesData,
    create_ioc_database_from_files,
)


@pytest.fixture
def mock_xml_data():
    """Create mock XML data for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<list version="15.1">
    <order>
        <latin_name>Passeriformes</latin_name>
        <family>
            <latin_name>Turdidae</latin_name>
            <genus>
                <latin_name>Turdus</latin_name>
                <authority>Linnaeus, 1758</authority>
                <species>
                    <latin_name>migratorius</latin_name>
                    <authority>Linnaeus, 1766</authority>
                    <english_name>American Robin</english_name>
                    <breeding_regions>NA</breeding_regions>
                    <breeding_subregions>widespread</breeding_subregions>
                </species>
                <species>
                    <latin_name>merula</latin_name>
                    <authority>Linnaeus, 1758</authority>
                    <english_name>Eurasian Blackbird</english_name>
                </species>
            </genus>
        </family>
    </order>
</list>"""


@pytest.fixture
def mock_xlsx_data():
    """Create mock XLSX workbook."""
    wb = MagicMock()
    ws = MagicMock()
    wb.active = ws

    # Mock headers
    headers = [
        MagicMock(value="seq"),
        MagicMock(value="Order"),
        MagicMock(value="Family"),
        MagicMock(value="IOC_15.1"),
        MagicMock(value="English"),
        MagicMock(value="Spanish"),
        MagicMock(value="French"),
    ]

    # Mock data rows
    row1 = [
        MagicMock(value=1),
        MagicMock(value="Passeriformes"),
        MagicMock(value="Turdidae"),
        MagicMock(value="Turdus migratorius"),
        MagicMock(value="American Robin"),
        MagicMock(value="Petirrojo Americano"),
        MagicMock(value="Merle d'Amérique"),
    ]

    row2 = [
        MagicMock(value=2),
        MagicMock(value="Passeriformes"),
        MagicMock(value="Turdidae"),
        MagicMock(value="Turdus merula"),
        MagicMock(value="Eurasian Blackbird"),
        MagicMock(value="Mirlo Común"),
        MagicMock(value="Merle noir"),
    ]

    ws.__getitem__ = lambda self, idx: headers if idx == 1 else None
    ws.max_row = 3

    def get_row(self, row_num):
        if row_num == 1:
            return headers
        elif row_num == 2:
            return row1
        elif row_num == 3:
            return row2
        return []

    ws.__getitem__ = get_row

    return wb


@pytest.fixture
def ioc_builder(tmp_path):
    """Create IOC database builder instance."""
    return IOCDatabaseBuilder(data_dir=tmp_path)


@pytest.fixture
def ioc_builder_with_db(tmp_path):
    """Create IOC database builder with database support."""
    db_path = tmp_path / "test_ioc.db"
    return IOCDatabaseBuilder(data_dir=tmp_path, db_path=db_path)


class TestIOCDatabaseBuilderXMLLoading:
    """Test XML data loading functionality."""

    def test_load_xml_data_success(self, ioc_builder, tmp_path, mock_xml_data):
        """Test successful XML data loading."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(mock_xml_data)

        ioc_builder._load_xml_data(xml_file)

        assert ioc_builder._ioc_version == "15.1"
        assert len(ioc_builder._species_data) == 2
        assert "Turdus migratorius" in ioc_builder._species_data
        assert "Turdus merula" in ioc_builder._species_data

        robin = ioc_builder._species_data["Turdus migratorius"]
        assert robin.english_name == "American Robin"
        assert robin.order == "Passeriformes"
        assert robin.family == "Turdidae"
        assert robin.genus == "Turdus"
        assert robin.species == "migratorius"
        assert robin.authority == "Linnaeus, 1766"
        assert robin.breeding_regions == "NA"

    def test_load_xml_data_parse_error(self, ioc_builder, tmp_path):
        """Test XML parse error handling."""
        xml_file = tmp_path / "invalid.xml"
        xml_file.write_text("Invalid XML content")

        with pytest.raises(ValueError, match="Failed to parse IOC XML"):
            ioc_builder._load_xml_data(xml_file)

    def test_find_ioc_xml_file(self, ioc_builder, tmp_path):
        """Test XML file auto-detection."""
        xml_file = tmp_path / "master_ioc-names_xml_v15.1.xml"
        xml_file.touch()

        found = ioc_builder._find_ioc_xml_file()
        assert found == xml_file


class TestIOCDatabaseBuilderXLSXLoading:
    """Test XLSX translation loading functionality."""

    def test_load_xlsx_translations_success(self, ioc_builder, tmp_path, mock_xlsx_data):
        """Test successful XLSX translation loading."""
        with patch("openpyxl.load_workbook", return_value=mock_xlsx_data):
            xlsx_file = tmp_path / "test.xlsx"
            xlsx_file.touch()

            ioc_builder._load_xlsx_translations(xlsx_file)

            assert "Turdus migratorius" in ioc_builder._translations
            assert "Turdus merula" in ioc_builder._translations

            robin_translations = ioc_builder._translations["Turdus migratorius"]
            assert robin_translations.get("es") == "Petirrojo Americano"
            assert robin_translations.get("fr") == "Merle d'Amérique"

    def test_find_ioc_xlsx_file(self, ioc_builder, tmp_path):
        """Test XLSX file auto-detection."""
        xlsx_file = tmp_path / "Multiling_IOC_v15.1.xlsx"
        xlsx_file.touch()

        found = ioc_builder._find_ioc_xlsx_file()
        assert found == xlsx_file


class TestIOCDatabaseBuilderDataAccess:
    """Test data access methods."""

    def test_get_ioc_common_name(self, ioc_builder):
        """Test getting English common name."""
        # Setup test data
        ioc_builder._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder._loaded = True

        name = ioc_builder.get_ioc_common_name("Turdus migratorius")
        assert name == "American Robin"

        name = ioc_builder.get_ioc_common_name("Unknown species")
        assert name is None

    def test_get_translated_common_name(self, ioc_builder):
        """Test getting translated common name."""
        ioc_builder._translations["Turdus migratorius"] = {"es": "Petirrojo Americano"}
        ioc_builder._loaded = True

        name = ioc_builder.get_translated_common_name("Turdus migratorius", "es")
        assert name == "Petirrojo Americano"

        name = ioc_builder.get_translated_common_name("Turdus migratorius", "de")
        assert name is None

    def test_search_species_by_common_name(self, ioc_builder):
        """Test searching species by common name."""
        ioc_builder._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder._loaded = True

        results = ioc_builder.search_species_by_common_name("robin")
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"

        results = ioc_builder.search_species_by_common_name("blackbird")
        assert len(results) == 0


class TestIOCDatabaseBuilderExport:
    """Test data export functionality."""

    def test_export_json(self, ioc_builder, tmp_path):
        """Test JSON export."""
        # Setup test data
        ioc_builder._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder._translations["Turdus migratorius"] = {"es": "Petirrojo Americano"}
        ioc_builder._ioc_version = "15.1"
        ioc_builder._loaded = True

        output_file = tmp_path / "test.json"
        ioc_builder.export_json(output_file)

        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        assert data["version"] == "15.1"
        assert data["species_count"] == 1
        assert "Turdus migratorius" in data["species"]
        assert "Turdus migratorius" in data["translations"]

    def test_export_json_compressed(self, ioc_builder, tmp_path):
        """Test compressed JSON export."""
        ioc_builder._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder._loaded = True

        output_file = tmp_path / "test.json.gz"
        ioc_builder.export_json(output_file, compress=True)

        assert output_file.exists()

        with gzip.open(output_file, "rt") as f:
            data = json.load(f)

        assert "Turdus migratorius" in data["species"]

    def test_load_from_json(self, ioc_builder, tmp_path):
        """Test loading from JSON."""
        json_data = {
            "version": "15.1",
            "species_count": 1,
            "species": {
                "Turdus migratorius": {
                    "scientific_name": "Turdus migratorius",
                    "english_name": "American Robin",
                    "order": "Passeriformes",
                    "family": "Turdidae",
                    "genus": "Turdus",
                    "species": "migratorius",
                    "authority": "Linnaeus, 1766",
                    "breeding_regions": None,
                    "breeding_subregions": None,
                }
            },
            "translations": {"Turdus migratorius": {"es": "Petirrojo Americano"}},
        }

        json_file = tmp_path / "test.json"
        with open(json_file, "w") as f:
            json.dump(json_data, f)

        ioc_builder.load_from_json(json_file)

        assert ioc_builder._loaded
        assert ioc_builder._ioc_version == "15.1"
        assert "Turdus migratorius" in ioc_builder._species_data
        assert ioc_builder._translations["Turdus migratorius"]["es"] == "Petirrojo Americano"


class TestIOCDatabaseBuilderDatabase:
    """Test database functionality."""

    def test_populate_database(self, ioc_builder_with_db):
        """Test database population."""
        # Setup test data
        ioc_builder_with_db._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder_with_db._translations["Turdus migratorius"] = {"es": "Petirrojo Americano"}
        ioc_builder_with_db._ioc_version = "15.1"
        ioc_builder_with_db._loaded = True

        ioc_builder_with_db.populate_database()

        # Verify data was inserted
        species = ioc_builder_with_db.get_species_by_scientific_name("Turdus migratorius")
        assert species is not None
        assert species.english_name == "American Robin"

        translation = ioc_builder_with_db.get_translation("Turdus migratorius", "es")
        assert translation == "Petirrojo Americano"

    def test_search_species_by_common_name_db(self, ioc_builder_with_db):
        """Test database search by common name."""
        # Setup and populate database
        ioc_builder_with_db._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder_with_db._loaded = True
        ioc_builder_with_db.populate_database()

        results = ioc_builder_with_db.search_species_by_common_name_db("robin")
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"

    def test_attach_detach_database(self, ioc_builder_with_db):
        """Test database attach/detach functionality."""
        # Create a mock session
        mock_session = MagicMock()

        ioc_builder_with_db.attach_to_session(mock_session, "test_alias")
        mock_session.execute.assert_called_once()

        # Verify attach SQL
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "ATTACH DATABASE" in sql_text
        assert "test_alias" in sql_text

        # Reset and test detach
        mock_session.reset_mock()
        ioc_builder_with_db.detach_from_session(mock_session, "test_alias")
        mock_session.execute.assert_called_once()

        # Verify detach SQL
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "DETACH DATABASE test_alias" in sql_text


class TestIOCDatabaseBuilderIntegration:
    """Test integration scenarios."""

    def test_create_ioc_database_from_files(self, tmp_path, mock_xml_data):
        """Test creating database from files."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(mock_xml_data)

        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()

        db_path = tmp_path / "test_ioc.db"

        with patch("openpyxl.load_workbook"):
            builder = create_ioc_database_from_files(xml_file, xlsx_file, db_path)

        assert builder.db_path == db_path
        assert db_path.exists()

    def test_performance_indexes_creation(self, ioc_builder_with_db):
        """Test that performance indexes are created."""
        # Setup and populate database
        ioc_builder_with_db._species_data["Turdus migratorius"] = IOCSpeciesData(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
        )
        ioc_builder_with_db._loaded = True
        ioc_builder_with_db.populate_database()

        # Check if indexes exist
        with ioc_builder_with_db.get_db() as session:
            result = session.execute(
                text("""
                SELECT name FROM sqlite_master
                WHERE type='index'
                AND name LIKE 'idx_%'
            """)
            ).fetchall()

            index_names = [row[0] for row in result]
            assert "idx_species_family" in index_names
            assert "idx_translations_scientific_language" in index_names
