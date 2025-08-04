"""Tests for IOC reference service."""

import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch
from xml.etree.ElementTree import ParseError

import pytest

from birdnetpi.services.ioc_reference_service import (
    IOCReferenceService,
    IOCSpecies,
    IOCTranslation,
)


@pytest.fixture
def mock_xml_data():
    """Create mock XML data for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
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
</list>'''


@pytest.fixture
def mock_xlsx_data():
    """Create mock XLSX data structure."""
    return {
        'headers': ['seq', 'Order', 'Family', 'IOC_15.1', 'English', 'Spanish', 'French', 'German'],
        'rows': [
            [1, 'Passeriformes', 'Turdidae', 'Turdus migratorius', 'American Robin', 'Petirrojo Americano', 'Merle d\'Amérique', 'Wanderdrossel'],
            [2, 'Passeriformes', 'Turdidae', 'Turdus merula', 'Eurasian Blackbird', 'Mirlo Común', 'Merle noir', 'Amsel'],
        ]
    }


@pytest.fixture
def ioc_service():
    """Create IOC reference service instance."""
    return IOCReferenceService()


@pytest.fixture
def populated_service(tmp_path):
    """Create IOC service with test data."""
    service = IOCReferenceService(data_dir=tmp_path)
    
    # Add test species data
    service._species_data = {
        "Turdus migratorius": IOCSpecies(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766"
        ),
        "Turdus merula": IOCSpecies(
            scientific_name="Turdus merula",
            english_name="Eurasian Blackbird",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="merula",
            authority="Linnaeus, 1758"
        )
    }
    
    # Add test translations
    service._translations = {
        "Turdus migratorius": {
            "es": "Petirrojo Americano",
            "fr": "Merle d'Amérique",
            "de": "Wanderdrossel"
        },
        "Turdus merula": {
            "es": "Mirlo Común",
            "fr": "Merle noir",
            "de": "Amsel"
        }
    }
    
    service._ioc_version = "15.1"
    service._loaded = True
    
    return service


class TestIOCSpecies:
    """Test IOCSpecies dataclass."""
    
    def test_ioc_species_creation(self):
        """Should create IOCSpecies with required fields."""
        species = IOCSpecies(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766"
        )
        
        assert species.scientific_name == "Turdus migratorius"
        assert species.english_name == "American Robin"
        assert species.order == "Passeriformes"
        assert species.family == "Turdidae"
        assert species.genus == "Turdus"
        assert species.species == "migratorius"
        assert species.authority == "Linnaeus, 1766"
        assert species.breeding_regions is None
        assert species.breeding_subregions is None
    
    def test_ioc_species_with_optional_fields(self):
        """Should create IOCSpecies with optional breeding region fields."""
        species = IOCSpecies(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
            breeding_regions="NA",
            breeding_subregions="widespread"
        )
        
        assert species.breeding_regions == "NA"
        assert species.breeding_subregions == "widespread"


class TestIOCTranslation:
    """Test IOCTranslation dataclass."""
    
    def test_ioc_translation_creation(self):
        """Should create IOCTranslation with all fields."""
        translation = IOCTranslation(
            scientific_name="Turdus migratorius",
            language_code="es",
            common_name="Petirrojo Americano"
        )
        
        assert translation.scientific_name == "Turdus migratorius"
        assert translation.language_code == "es"
        assert translation.common_name == "Petirrojo Americano"


class TestIOCReferenceServiceInitialization:
    """Test IOC reference service initialization."""
    
    def test_service_initialization_default(self):
        """Should initialize service with default data directory."""
        service = IOCReferenceService()
        
        assert service.data_dir == Path(".")
        assert service._species_data == {}
        assert service._translations == {}
        assert service._ioc_version == "unknown"
        assert service._loaded is False
    
    def test_service_initialization_custom_dir(self, tmp_path):
        """Should initialize service with custom data directory."""
        service = IOCReferenceService(data_dir=tmp_path)
        
        assert service.data_dir == tmp_path
        assert service._species_data == {}
        assert service._translations == {}
        assert service._ioc_version == "unknown" 
        assert service._loaded is False


class TestFileDetection:
    """Test IOC file detection methods."""
    
    def test_find_ioc_xml_file_found(self, tmp_path):
        """Should find IOC XML file using patterns."""
        xml_file = tmp_path / "ioc_names_v15.1.xml"
        xml_file.touch()
        
        service = IOCReferenceService(data_dir=tmp_path)
        found_file = service._find_ioc_xml_file()
        
        assert found_file == xml_file
    
    def test_find_ioc_xml_file_not_found(self, tmp_path):
        """Should return None when XML file not found."""
        service = IOCReferenceService(data_dir=tmp_path)
        found_file = service._find_ioc_xml_file()
        
        assert found_file is None
    
    def test_find_ioc_xlsx_file_found(self, tmp_path):
        """Should find IOC XLSX file using patterns."""
        xlsx_file = tmp_path / "multiling_IOC_v15.1.xlsx"
        xlsx_file.touch()
        
        service = IOCReferenceService(data_dir=tmp_path)
        found_file = service._find_ioc_xlsx_file()
        
        assert found_file == xlsx_file
    
    def test_find_ioc_xlsx_file_not_found(self, tmp_path):
        """Should return None when XLSX file not found."""
        service = IOCReferenceService(data_dir=tmp_path)
        found_file = service._find_ioc_xlsx_file()
        
        assert found_file is None


class TestXMLLoading:
    """Test XML data loading functionality."""
    
    @patch("birdnetpi.services.ioc_reference_service.ET.parse")
    def test_load_xml_data_success(self, mock_parse, ioc_service, mock_xml_data, tmp_path):
        """Should load XML data successfully."""
        # Setup mock XML parsing
        mock_tree = MagicMock()
        mock_root = ET.fromstring(mock_xml_data)
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree
        
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(mock_xml_data)
        
        ioc_service._load_xml_data(xml_file)
        
        assert ioc_service._ioc_version == "15.1"
        assert len(ioc_service._species_data) == 2
        assert "Turdus migratorius" in ioc_service._species_data
        assert "Turdus merula" in ioc_service._species_data
        
        robin = ioc_service._species_data["Turdus migratorius"]
        assert robin.english_name == "American Robin"
        assert robin.order == "Passeriformes"
        assert robin.family == "Turdidae"
        assert robin.genus == "Turdus"
        assert robin.species == "migratorius"
        assert robin.authority == "Linnaeus, 1766"
        assert robin.breeding_regions == "NA"
    
    @patch("birdnetpi.services.ioc_reference_service.ET.parse")
    def test_load_xml_data_parse_error(self, mock_parse, ioc_service, tmp_path):
        """Should handle XML parse errors gracefully."""
        mock_parse.side_effect = ParseError("Invalid XML")
        
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("invalid xml")
        
        with pytest.raises(ValueError, match="Failed to parse IOC XML file"):
            ioc_service._load_xml_data(xml_file)
    
    @patch("birdnetpi.services.ioc_reference_service.ET.parse")
    def test_load_xml_data_general_error(self, mock_parse, ioc_service, tmp_path):
        """Should handle general XML loading errors."""
        mock_parse.side_effect = Exception("File read error")
        
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("xml content")
        
        with pytest.raises(ValueError, match="Failed to load IOC XML data"):
            ioc_service._load_xml_data(xml_file)
    
    def test_get_element_text_found(self, ioc_service):
        """Should get element text when element exists."""
        parent = ET.fromstring("<parent><child>test text</child></parent>")
        
        result = ioc_service._get_element_text(parent, "child", "default")
        
        assert result == "test text"
    
    def test_get_element_text_not_found(self, ioc_service):
        """Should return default when element not found."""
        parent = ET.fromstring("<parent></parent>")
        
        result = ioc_service._get_element_text(parent, "missing", "default")
        
        assert result == "default"
    
    def test_get_element_text_empty(self, ioc_service):
        """Should return default when element is empty."""
        parent = ET.fromstring("<parent><child></child></parent>")
        
        result = ioc_service._get_element_text(parent, "child", "default")
        
        assert result == "default"


class TestXLSXLoading:
    """Test XLSX translation loading functionality."""
    
    @patch("birdnetpi.services.ioc_reference_service.openpyxl.load_workbook")
    def test_load_xlsx_translations_success(self, mock_load_workbook, ioc_service, mock_xlsx_data, tmp_path):
        """Should load XLSX translations successfully."""
        # Setup mock workbook
        mock_workbook = MagicMock()
        mock_worksheet = MagicMock()
        mock_workbook.active = mock_worksheet
        mock_load_workbook.return_value = mock_workbook
        
        # Mock worksheet rows
        headers = mock_xlsx_data['headers']
        rows = mock_xlsx_data['rows']
        
        # Set up proper indexing for all rows
        def getitem_side_effect(index):
            if index == 1:  # Header row
                return [MagicMock(value=h) for h in headers]
            elif 2 <= index <= len(rows) + 1:  # Data rows
                row_data = rows[index - 2]
                return [MagicMock(value=row_data[j] if j < len(row_data) else None) for j in range(len(headers))]
            return []
        
        mock_worksheet.__getitem__.side_effect = getitem_side_effect
        mock_worksheet.max_row = len(rows) + 1
        
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        
        ioc_service._load_xlsx_translations(xlsx_file)
        
        assert "Turdus migratorius" in ioc_service._translations
        assert "Turdus merula" in ioc_service._translations
        
        robin_translations = ioc_service._translations["Turdus migratorius"]
        assert robin_translations.get("es") == "Petirrojo Americano"
        assert robin_translations.get("fr") == "Merle d'Amérique"
        assert robin_translations.get("de") == "Wanderdrossel"
    
    @patch("birdnetpi.services.ioc_reference_service.openpyxl.load_workbook")
    def test_load_xlsx_translations_no_worksheet(self, mock_load_workbook, ioc_service, tmp_path):
        """Should handle missing worksheet error."""
        mock_workbook = MagicMock()
        mock_workbook.active = None
        mock_load_workbook.return_value = mock_workbook
        
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        
        with pytest.raises(ValueError, match="Worksheet is None"):
            ioc_service._load_xlsx_translations(xlsx_file)
    
    @patch("birdnetpi.services.ioc_reference_service.openpyxl.load_workbook")
    def test_load_xlsx_translations_file_error(self, mock_load_workbook, ioc_service, tmp_path):
        """Should handle XLSX file loading errors."""
        mock_load_workbook.side_effect = Exception("File read error")
        
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.touch()
        
        with pytest.raises(ValueError, match="Failed to load IOC XLSX translations"):
            ioc_service._load_xlsx_translations(xlsx_file)
    
    def test_map_language_to_code_known_languages(self, ioc_service):
        """Should map known language names to ISO codes."""
        test_cases = [
            ("Spanish", "es"),
            ("French", "fr"),
            ("German", "de"),
            ("Portuguese (Lusophone)", "pt"),
            ("Chinese (Traditional)", "zh-TW"),
            ("Northern Sami", "se"),
        ]
        
        for language_name, expected_code in test_cases:
            result = ioc_service._map_language_to_code(language_name)
            assert result == expected_code
    
    def test_map_language_to_code_unknown_language(self, ioc_service):
        """Should return None for unknown language names."""
        result = ioc_service._map_language_to_code("Unknown Language")
        assert result is None


class TestDataLoading:
    """Test main data loading functionality."""
    
    @patch.object(IOCReferenceService, "_load_xlsx_translations")
    @patch.object(IOCReferenceService, "_load_xml_data")
    @patch.object(IOCReferenceService, "_find_ioc_xlsx_file")
    @patch.object(IOCReferenceService, "_find_ioc_xml_file")
    def test_load_ioc_data_auto_detect_files(self, mock_find_xml, mock_find_xlsx, 
                                           mock_load_xml, mock_load_xlsx, ioc_service, tmp_path):
        """Should auto-detect and load IOC files."""
        xml_file = tmp_path / "ioc.xml"
        xlsx_file = tmp_path / "ioc.xlsx"
        
        mock_find_xml.return_value = xml_file
        mock_find_xlsx.return_value = xlsx_file
        
        # Mock file existence
        with patch.object(Path, "exists", return_value=True):
            ioc_service.load_ioc_data()
        
        mock_load_xml.assert_called_once_with(xml_file)
        mock_load_xlsx.assert_called_once_with(xlsx_file)
        assert ioc_service._loaded is True
    
    @patch.object(IOCReferenceService, "_load_xlsx_translations")
    @patch.object(IOCReferenceService, "_load_xml_data")
    def test_load_ioc_data_explicit_files(self, mock_load_xml, mock_load_xlsx, ioc_service, tmp_path):
        """Should load IOC data from explicitly provided files."""
        xml_file = tmp_path / "custom.xml"
        xlsx_file = tmp_path / "custom.xlsx"
        
        # Mock file existence
        with patch.object(Path, "exists", return_value=True):
            ioc_service.load_ioc_data(xml_file=xml_file, xlsx_file=xlsx_file)
        
        mock_load_xml.assert_called_once_with(xml_file)
        mock_load_xlsx.assert_called_once_with(xlsx_file)
        assert ioc_service._loaded is True
    
    def test_load_ioc_data_already_loaded(self, populated_service):
        """Should skip loading when already loaded and not forcing reload."""
        with patch.object(populated_service, "_load_xml_data") as mock_load_xml:
            populated_service.load_ioc_data()
            mock_load_xml.assert_not_called()
    
    @patch.object(IOCReferenceService, "_load_xml_data")
    def test_load_ioc_data_force_reload(self, mock_load_xml, populated_service, tmp_path):
        """Should reload data when force_reload is True."""
        xml_file = tmp_path / "test.xml"
        
        with patch.object(Path, "exists", return_value=True):
            populated_service.load_ioc_data(xml_file=xml_file, force_reload=True)
        
        mock_load_xml.assert_called_once_with(xml_file)


class TestSpeciesLookup:
    """Test species lookup functionality."""
    
    def test_get_ioc_common_name_found(self, populated_service):
        """Should return IOC common name for known species."""
        result = populated_service.get_ioc_common_name("Turdus migratorius")
        assert result == "American Robin"
    
    def test_get_ioc_common_name_not_found(self, populated_service):
        """Should return None for unknown species."""
        result = populated_service.get_ioc_common_name("Nonexistent species")
        assert result is None
    
    @patch.object(IOCReferenceService, "load_ioc_data")
    def test_get_ioc_common_name_auto_load(self, mock_load, ioc_service):
        """Should auto-load data when not loaded."""
        ioc_service.get_ioc_common_name("Turdus migratorius")
        mock_load.assert_called_once()
    
    def test_get_translated_common_name_found(self, populated_service):
        """Should return translated name for known species and language."""
        result = populated_service.get_translated_common_name("Turdus migratorius", "es")
        assert result == "Petirrojo Americano"
    
    def test_get_translated_common_name_not_found(self, populated_service):
        """Should return None for unknown species or language."""
        result = populated_service.get_translated_common_name("Turdus migratorius", "unknown")
        assert result is None
    
    def test_get_species_info_found(self, populated_service):
        """Should return complete species info for known species."""
        result = populated_service.get_species_info("Turdus migratorius")
        
        assert result is not None
        assert result.scientific_name == "Turdus migratorius"
        assert result.english_name == "American Robin"
        assert result.order == "Passeriformes"
        assert result.family == "Turdidae"
    
    def test_get_species_info_not_found(self, populated_service):
        """Should return None for unknown species."""
        result = populated_service.get_species_info("Nonexistent species")
        assert result is None


class TestSpeciesSearch:
    """Test species search functionality."""
    
    def test_search_species_by_common_name_english(self, populated_service):
        """Should search species by English common name."""
        results = populated_service.search_species_by_common_name("Robin")
        
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"
        assert results[0].english_name == "American Robin"
    
    def test_search_species_by_common_name_translated(self, populated_service):
        """Should search species by translated common name."""
        results = populated_service.search_species_by_common_name("Petirrojo", "es")
        
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"
    
    def test_search_species_by_common_name_case_insensitive(self, populated_service):
        """Should perform case-insensitive search."""
        results = populated_service.search_species_by_common_name("ROBIN")
        
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"
    
    def test_search_species_by_common_name_partial_match(self, populated_service):
        """Should find partial matches."""
        results = populated_service.search_species_by_common_name("Black")
        
        assert len(results) == 1
        assert results[0].scientific_name == "Turdus merula"
        assert "Blackbird" in results[0].english_name
    
    def test_search_species_by_common_name_no_results(self, populated_service):
        """Should return empty list when no matches found."""
        results = populated_service.search_species_by_common_name("Nonexistent")
        assert results == []


class TestDataAccess:
    """Test data access methods."""
    
    def test_get_available_languages(self, populated_service):
        """Should return set of available language codes."""
        languages = populated_service.get_available_languages()
        
        expected_languages = {"es", "fr", "de"}
        assert languages == expected_languages
    
    def test_get_species_count(self, populated_service):
        """Should return total number of species."""
        count = populated_service.get_species_count()
        assert count == 2
    
    def test_get_ioc_version(self, populated_service):
        """Should return IOC version."""
        version = populated_service.get_ioc_version()
        assert version == "15.1"
    
    @patch.object(IOCReferenceService, "load_ioc_data")
    def test_methods_auto_load_data(self, mock_load, ioc_service):
        """Should auto-load data when accessing methods on unloaded service."""
        methods_to_test = [
            lambda: ioc_service.get_available_languages(),
            lambda: ioc_service.get_species_count(),
            lambda: ioc_service.get_ioc_version(),
        ]
        
        for method in methods_to_test:
            mock_load.reset_mock()
            method()
            mock_load.assert_called_once()


class TestJSONExport:
    """Test JSON export functionality."""
    
    def test_export_json_uncompressed(self, populated_service, tmp_path):
        """Should export IOC data to uncompressed JSON."""
        output_file = tmp_path / "test.json"
        
        populated_service.export_json(output_file, include_translations=True, compress=False)
        
        assert output_file.exists()
        
        with open(output_file) as f:
            data = json.load(f)
        
        assert data["version"] == "15.1"
        assert data["species_count"] == 2
        assert "Turdus migratorius" in data["species"]
        assert "translations" in data
        assert "available_languages" in data
    
    def test_export_json_compressed(self, populated_service, tmp_path):
        """Should export IOC data to compressed JSON."""
        output_file = tmp_path / "test.json.gz"
        
        populated_service.export_json(output_file, include_translations=True, compress=True)
        
        assert output_file.exists()
        
        with gzip.open(output_file, "rt", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data["version"] == "15.1"
        assert data["species_count"] == 2
    
    def test_export_json_without_translations(self, populated_service, tmp_path):
        """Should export IOC data without translations."""
        output_file = tmp_path / "test.json"
        
        populated_service.export_json(output_file, include_translations=False, compress=False)
        
        with open(output_file) as f:
            data = json.load(f)
        
        assert "translations" not in data
        assert "available_languages" not in data
        assert "species" in data


class TestJSONImport:
    """Test JSON import functionality."""
    
    def test_load_from_json_uncompressed(self, ioc_service, tmp_path):
        """Should load IOC data from uncompressed JSON."""
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
                    "breeding_subregions": None
                }
            },
            "translations": {
                "Turdus migratorius": {
                    "es": "Petirrojo Americano"
                }
            }
        }
        
        json_file = tmp_path / "test.json"
        with open(json_file, "w") as f:
            json.dump(json_data, f)
        
        ioc_service.load_from_json(json_file)
        
        assert ioc_service._ioc_version == "15.1"
        assert len(ioc_service._species_data) == 1
        assert "Turdus migratorius" in ioc_service._species_data
        assert ioc_service._translations["Turdus migratorius"]["es"] == "Petirrojo Americano"
        assert ioc_service._loaded is True
    
    def test_load_from_json_compressed(self, ioc_service, tmp_path):
        """Should load IOC data from compressed JSON."""
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
                    "breeding_subregions": None
                }
            },
            "translations": {}
        }
        
        json_file = tmp_path / "test.json.gz"
        with gzip.open(json_file, "wt", encoding="utf-8") as f:
            json.dump(json_data, f)
        
        ioc_service.load_from_json(json_file)
        
        assert ioc_service._ioc_version == "15.1"
        assert len(ioc_service._species_data) == 1
        assert ioc_service._loaded is True
    
    def test_load_from_json_auto_detect_compression(self, ioc_service, tmp_path):
        """Should auto-detect compression from file extension."""
        json_data = {"version": "15.1", "species": {}, "translations": {}}
        
        # Test .gz extension
        gz_file = tmp_path / "test.json.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(json_data, f)
        
        ioc_service.load_from_json(gz_file)
        assert ioc_service._ioc_version == "15.1"
    
    def test_load_from_json_explicit_compression(self, ioc_service, tmp_path):
        """Should respect explicit compression parameter."""
        json_data = {"version": "15.1", "species": {}, "translations": {}}
        
        # Create compressed file with non-standard name
        json_file = tmp_path / "test.data"
        with gzip.open(json_file, "wt", encoding="utf-8") as f:
            json.dump(json_data, f)
        
        ioc_service.load_from_json(json_file, compressed=True)
        assert ioc_service._ioc_version == "15.1"


class TestErrorHandling:
    """Test error handling across the service."""
    
    def test_xml_parsing_error_handling(self, ioc_service, tmp_path):
        """Should handle XML parsing errors gracefully."""
        xml_file = tmp_path / "invalid.xml"
        xml_file.write_text("invalid xml content")
        
        with pytest.raises(ValueError, match="Failed to parse IOC XML file"):
            ioc_service._load_xml_data(xml_file)
    
    def test_json_file_not_found(self, ioc_service, tmp_path):
        """Should handle missing JSON file."""
        missing_file = tmp_path / "missing.json"
        
        with pytest.raises(FileNotFoundError):
            ioc_service.load_from_json(missing_file)
    
    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    def test_json_permission_error(self, mock_open, ioc_service, tmp_path):
        """Should handle permission errors when reading JSON."""
        json_file = tmp_path / "test.json"
        json_file.touch()
        
        with pytest.raises(PermissionError):
            ioc_service.load_from_json(json_file)


class TestIntegration:
    """Integration tests for IOC reference service."""
    
    @patch("birdnetpi.services.ioc_reference_service.ET.parse")
    @patch("birdnetpi.services.ioc_reference_service.openpyxl.load_workbook") 
    def test_complete_workflow(self, mock_load_workbook, mock_parse, tmp_path):
        """Should complete full workflow from XML/XLSX to JSON and back."""
        # Setup XML mock
        mock_tree = MagicMock()
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
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
                        </species>
                    </genus>
                </family>
            </order>
        </list>'''
        mock_root = ET.fromstring(xml_content)
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree
        
        # Setup XLSX mock
        mock_workbook = MagicMock()
        mock_worksheet = MagicMock()
        mock_workbook.active = mock_worksheet
        mock_load_workbook.return_value = mock_workbook
        
        headers = ['seq', 'Order', 'Family', 'IOC_15.1', 'English', 'Spanish']
        rows = [[1, 'Passeriformes', 'Turdidae', 'Turdus migratorius', 'American Robin', 'Petirrojo Americano']]
        
        def getitem_side_effect(index):
            if index == 1:  # Header row
                return [MagicMock(value=h) for h in headers]
            elif index == 2:  # Data row
                return [MagicMock(value=rows[0][j] if j < len(rows[0]) else None) for j in range(len(headers))]
            return []
        
        mock_worksheet.__getitem__.side_effect = getitem_side_effect
        mock_worksheet.max_row = 2
        
        # Create service and load data
        service = IOCReferenceService(data_dir=tmp_path)
        xml_file = tmp_path / "test.xml"
        xlsx_file = tmp_path / "test.xlsx"
        xml_file.write_text(xml_content)
        xlsx_file.touch()
        
        service.load_ioc_data(xml_file=xml_file, xlsx_file=xlsx_file)
        
        # Verify loaded data
        assert service._ioc_version == "15.1"
        assert len(service._species_data) == 1
        assert "Turdus migratorius" in service._species_data
        
        # Test species lookup
        species = service.get_species_info("Turdus migratorius")
        assert species is not None
        assert species.english_name == "American Robin"
        
        # Test translation
        translation = service.get_translated_common_name("Turdus migratorius", "es")
        assert translation == "Petirrojo Americano"
        
        # Export to JSON
        json_file = tmp_path / "export.json"
        service.export_json(json_file, include_translations=True)
        
        # Load from JSON into new service
        new_service = IOCReferenceService()
        new_service.load_from_json(json_file)
        
        # Verify round-trip integrity
        assert new_service._ioc_version == "15.1"
        assert len(new_service._species_data) == 1
        
        new_species = new_service.get_species_info("Turdus migratorius")
        assert new_species is not None
        assert new_species.english_name == "American Robin"
        
        new_translation = new_service.get_translated_common_name("Turdus migratorius", "es")
        assert new_translation == "Petirrojo Americano"
    
    def test_edge_case_handling(self, tmp_path):
        """Should handle various edge cases gracefully."""
        service = IOCReferenceService(data_dir=tmp_path)
        
        # Test empty service behavior
        assert service.get_species_count() == 0
        assert service.get_available_languages() == set()
        assert service.get_ioc_version() == "unknown"
        assert service.get_species_info("any species") is None
        assert service.get_ioc_common_name("any species") is None
        assert service.get_translated_common_name("any species", "en") is None
        assert service.search_species_by_common_name("any name") == []