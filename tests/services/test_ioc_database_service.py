"""Tests for IOC database service."""

import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from birdnetpi.models.ioc_database_models import (
    IOCLanguage,
    IOCMetadata,
    IOCSpecies,
    IOCTranslation,
)
from birdnetpi.services.ioc_database_service import (
    IOCDatabaseService,
    create_ioc_database_from_files,
)
from birdnetpi.services.ioc_reference_service import (
    IOCReferenceService,
)
from birdnetpi.services.ioc_reference_service import (
    IOCSpecies as RefIOCSpecies,
)


@pytest.fixture
def temp_db_path():
    """Create temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def ioc_database_service(temp_db_path):
    """Create IOC database service instance."""
    return IOCDatabaseService(temp_db_path)


@pytest.fixture
def mock_ioc_reference_service():
    """Create mock IOC reference service with test data."""
    mock_service = MagicMock(spec=IOCReferenceService)
    mock_service._loaded = True

    # Mock species data
    mock_service._species_data = {
        "Turdus migratorius": RefIOCSpecies(
            scientific_name="Turdus migratorius",
            english_name="American Robin",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="migratorius",
            authority="Linnaeus, 1766",
            breeding_regions="NA",
            breeding_subregions="widespread",
        ),
        "Turdus merula": RefIOCSpecies(
            scientific_name="Turdus merula",
            english_name="Eurasian Blackbird",
            order="Passeriformes",
            family="Turdidae",
            genus="Turdus",
            species="merula",
            authority="Linnaeus, 1758",
            breeding_regions=None,
            breeding_subregions=None,
        ),
    }

    # Mock translations
    mock_service._translations = {
        "Turdus migratorius": {
            "es": "Petirrojo Americano",
            "fr": "Merle d'Amérique",
            "de": "Wanderdrossel",
        },
        "Turdus merula": {"es": "Mirlo Común", "fr": "Merle noir", "de": "Amsel"},
    }

    mock_service.get_ioc_version.return_value = "15.1"
    return mock_service


@pytest.fixture
def populated_ioc_database_service(ioc_database_service, mock_ioc_reference_service):
    """Create populated database service."""
    ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)
    return ioc_database_service


class TestIOCDatabaseServiceInitialization:
    """Test IOC database service initialization."""

    def test_service_initialization(self, temp_db_path):
        """Should initialize service and create database schema."""
        service = IOCDatabaseService(temp_db_path)

        assert service.db_path == temp_db_path
        assert os.path.exists(temp_db_path)
        assert service.engine is not None
        assert service.session_local is not None

    def test_service_creates_directory(self, tmp_path):
        """Should create directory structure if it doesn't exist."""
        db_path = str(tmp_path / "subdir" / "test.db")

        service = IOCDatabaseService(db_path)

        assert os.path.exists(os.path.dirname(db_path))
        assert service.db_path == db_path


class TestPopulateFromIOCService:
    """Test database population from IOC reference service."""

    def test_populate(self, ioc_database_service, mock_ioc_reference_service, capsys):
        """Should populate database successfully."""
        ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)

        # Verify species were inserted
        session = ioc_database_service.session_local()
        try:
            species_count = session.query(IOCSpecies).count()
            assert species_count == 2

            # Check specific species
            robin = (
                session.query(IOCSpecies).filter_by(scientific_name="Turdus migratorius").first()
            )
            assert robin is not None
            assert robin.english_name == "American Robin"
            assert robin.order_name == "Passeriformes"
            assert robin.family == "Turdidae"
            assert robin.genus == "Turdus"
            assert robin.species_epithet == "migratorius"
            assert robin.authority == "Linnaeus, 1766"
            assert robin.breeding_regions == "NA"
            assert robin.breeding_subregions == "widespread"

            # Verify translations were inserted
            translation_count = session.query(IOCTranslation).count()
            assert translation_count == 6  # 2 species * 3 languages each

            # Check specific translation
            translation = (
                session.query(IOCTranslation)
                .filter_by(scientific_name="Turdus migratorius", language_code="es")
                .first()
            )
            assert translation is not None
            assert translation.common_name == "Petirrojo Americano"

            # Verify languages were inserted
            language_count = session.query(IOCLanguage).count()
            assert language_count == 3  # es, fr, de

            # Verify metadata was inserted
            metadata_count = session.query(IOCMetadata).count()
            assert (
                metadata_count == 5
            )  # ioc_version, created_at, species_count, translation_count, languages_available

            version_metadata = session.query(IOCMetadata).filter_by(key="ioc_version").first()
            assert version_metadata is not None
            assert version_metadata.value == "15.1"

        finally:
            session.close()

        # Check console output
        captured = capsys.readouterr()
        assert "Inserted 2 species total" in captured.out
        assert "Inserted 6 translations total" in captured.out
        assert "IOC database populated successfully" in captured.out

    def test_populate_service_not_loaded(self, ioc_database_service):
        """Should raise error if IOC service not loaded."""
        mock_service = MagicMock()
        mock_service._loaded = False

        with pytest.raises(ValueError, match="IOC service must be loaded"):
            ioc_database_service.populate_from_ioc_service(mock_service)

    def test_populate_clears_existing_data(
        self, populated_ioc_database_service, mock_ioc_reference_service
    ):
        """Should clear existing data before repopulating."""
        # Verify initial data exists
        session = populated_ioc_database_service.session_local()
        try:
            initial_count = session.query(IOCSpecies).count()
            assert initial_count == 2
        finally:
            session.close()

        # Repopulate with same data
        populated_ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)

        # Verify data was cleared and repopulated (not duplicated)
        session = populated_ioc_database_service.session_local()
        try:
            final_count = session.query(IOCSpecies).count()
            assert final_count == 2
        finally:
            session.close()

    @patch("birdnetpi.services.ioc_database_service.datetime")
    def test_populate__mocked_datetime(
        self, mock_datetime, ioc_database_service, mock_ioc_reference_service
    ):
        """Should use current datetime for metadata."""
        mock_now = datetime(2025, 1, 15, 10, 30, 0)
        mock_datetime.utcnow.return_value = mock_now

        ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)

        session = ioc_database_service.session_local()
        try:
            created_metadata = session.query(IOCMetadata).filter_by(key="created_at").first()
            assert created_metadata is not None
            assert created_metadata.value == "2025-01-15T10:30:00"
        finally:
            session.close()

    def test_populate_database_error(self, ioc_database_service, mock_ioc_reference_service):
        """Should handle database errors gracefully."""
        # Mock session to raise exception during commit
        with patch.object(ioc_database_service, "session_local") as mock_session_local:
            mock_session = MagicMock()
            mock_session.bulk_insert_mappings.side_effect = Exception("Database error")
            mock_session_local.return_value = mock_session

            with pytest.raises(RuntimeError, match="Failed to populate IOC database"):
                ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)

            # Verify rollback was called
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()


class TestSpeciesLookup:
    """Test species lookup functionality."""

    def test_get_species_by_scientific_name_found(self, populated_ioc_database_service):
        """Should return species when found."""
        species = populated_ioc_database_service.get_species_by_scientific_name(
            "Turdus migratorius"
        )

        assert species is not None
        assert species.scientific_name == "Turdus migratorius"
        assert species.english_name == "American Robin"
        assert species.order_name == "Passeriformes"
        assert species.family == "Turdidae"

    def test_get_species_by_scientific_name_not_found(self, populated_ioc_database_service):
        """Should return None when species not found."""
        species = populated_ioc_database_service.get_species_by_scientific_name(
            "Nonexistent species"
        )
        assert species is None

    def test_get_species_by_scientific_name__empty_string(self, populated_ioc_database_service):
        """Should handle empty string gracefully."""
        species = populated_ioc_database_service.get_species_by_scientific_name("")
        assert species is None


class TestTranslationLookup:
    """Test translation lookup functionality."""

    def test_get_translation_found(self, populated_ioc_database_service):
        """Should return translation when found."""
        translation = populated_ioc_database_service.get_translation("Turdus migratorius", "es")
        assert translation == "Petirrojo Americano"

    def test_get_translation_not_found_species(self, populated_ioc_database_service):
        """Should return None for unknown species."""
        translation = populated_ioc_database_service.get_translation("Nonexistent species", "es")
        assert translation is None

    def test_get_translation_not_found_language(self, populated_ioc_database_service):
        """Should return None for unknown language."""
        translation = populated_ioc_database_service.get_translation(
            "Turdus migratorius", "unknown"
        )
        assert translation is None

    def test_get_translation__empty_parameters(self, populated_ioc_database_service):
        """Should handle empty parameters gracefully."""
        translation = populated_ioc_database_service.get_translation("", "")
        assert translation is None


class TestSpeciesSearch:
    """Test species search functionality."""

    def test_search_species_by_common_name_english(self, populated_ioc_database_service):
        """Should search English names successfully."""
        results = populated_ioc_database_service.search_species_by_common_name("Robin", "en")

        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"
        assert results[0].english_name == "American Robin"

    def test_search_species_by_common_name_case_insensitive(self, populated_ioc_database_service):
        """Should perform case-insensitive search."""
        results = populated_ioc_database_service.search_species_by_common_name("ROBIN", "en")

        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"

    def test_search_species_by_common_name_partial_match(self, populated_ioc_database_service):
        """Should find partial matches."""
        results = populated_ioc_database_service.search_species_by_common_name("Black", "en")

        assert len(results) == 1
        assert results[0].scientific_name == "Turdus merula"
        assert "Blackbird" in results[0].english_name

    def test_search_species_by_common_name_translated(self, populated_ioc_database_service):
        """Should search translated names."""
        results = populated_ioc_database_service.search_species_by_common_name("Petirrojo", "es")

        assert len(results) == 1
        assert results[0].scientific_name == "Turdus migratorius"

    def test_search_species_by_common_name__no_results(self, populated_ioc_database_service):
        """Should return empty list when no matches found."""
        results = populated_ioc_database_service.search_species_by_common_name("Nonexistent", "en")
        assert results == []

    def test_search_species_by_common_name__limit(self, populated_ioc_database_service):
        """Should respect limit parameter."""
        results = populated_ioc_database_service.search_species_by_common_name(
            "Turdus", "en", limit=1
        )
        assert len(results) <= 1

    def test_search_species_by_common_name__empty_search(self, populated_ioc_database_service):
        """Should handle empty search term."""
        results = populated_ioc_database_service.search_species_by_common_name("", "en")
        # Empty search should match all species
        assert len(results) == 2


class TestLanguageMetadata:
    """Test language metadata functionality."""

    def test_get_available_languages(self, populated_ioc_database_service):
        """Should return available languages."""
        languages = populated_ioc_database_service.get_available_languages()

        assert len(languages) == 3
        language_codes = [lang.language_code for lang in languages]
        assert "es" in language_codes
        assert "fr" in language_codes
        assert "de" in language_codes

        # Check specific language details
        spanish_lang = next(lang for lang in languages if lang.language_code == "es")
        assert spanish_lang.language_name == "Spanish"
        assert spanish_lang.translation_count == 2  # 2 species with Spanish translations

    def test_get_available_languages__empty_db(self, ioc_database_service):
        """Should return empty list for empty database."""
        languages = ioc_database_service.get_available_languages()
        assert languages == []


class TestMetadata:
    """Test metadata functionality."""

    def test_get_metadata(self, populated_ioc_database_service):
        """Should return all metadata."""
        metadata = populated_ioc_database_service.get_metadata()

        assert isinstance(metadata, dict)
        assert "ioc_version" in metadata
        assert metadata["ioc_version"] == "15.1"
        assert "species_count" in metadata
        assert metadata["species_count"] == "2"
        assert "translation_count" in metadata
        assert metadata["translation_count"] == "6"
        assert "languages_available" in metadata
        assert "created_at" in metadata

        # Check languages_available format
        languages = metadata["languages_available"].split(",")
        assert len(languages) == 3
        assert "es" in languages
        assert "fr" in languages
        assert "de" in languages

    def test_get_metadata__empty_db(self, ioc_database_service):
        """Should return empty dict for empty database."""
        metadata = ioc_database_service.get_metadata()
        assert metadata == {}


class TestDatabaseUtilities:
    """Test database utility functions."""

    def test_get_database_size_exists(self, populated_ioc_database_service):
        """Should return database file size when file exists."""
        size = populated_ioc_database_service.get_database_size()
        assert size > 0
        assert isinstance(size, int)

    def test_get_database_size_not_exists(self, tmp_path):
        """Should return 0 when database file doesn't exist."""
        db_path = str(tmp_path / "nonexistent.db")
        service = IOCDatabaseService.__new__(IOCDatabaseService)
        service.db_path = db_path

        size = service.get_database_size()
        assert size == 0


class TestDatabaseAttachment:
    """Test database attachment functionality."""

    def test_attach_to_session(self, populated_ioc_database_service):
        """Should attach database to session."""
        session = populated_ioc_database_service.session_local()
        try:
            # Attach database
            populated_ioc_database_service.attach_to_session(session, "test_ioc")

            # Verify attachment by querying attached database
            result = session.execute(
                text("SELECT name FROM test_ioc.sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]

            expected_tables = ["species", "translations", "metadata", "languages"]
            for table in expected_tables:
                assert table in tables

        finally:
            try:
                populated_ioc_database_service.detach_from_session(session, "test_ioc")
            except Exception:
                pass  # Ignore errors during cleanup
            session.close()

    def test_detach_from_session(self, populated_ioc_database_service):
        """Should detach database from session."""
        session = populated_ioc_database_service.session_local()
        try:
            # Attach and then detach
            populated_ioc_database_service.attach_to_session(session, "test_ioc")
            populated_ioc_database_service.detach_from_session(session, "test_ioc")

            # Verify detachment by trying to query (should fail)
            with pytest.raises(OperationalError):
                session.execute(text("SELECT * FROM test_ioc.species LIMIT 1"))

        finally:
            session.close()

    def test_attach__custom_alias(self, populated_ioc_database_service):
        """Should attach database with custom alias."""
        session = populated_ioc_database_service.session_local()
        alias = "custom_alias"
        try:
            populated_ioc_database_service.attach_to_session(session, alias)

            # Verify attachment with custom alias
            result = session.execute(
                text(f"SELECT name FROM {alias}.sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]
            assert "species" in tables

        finally:
            try:
                populated_ioc_database_service.detach_from_session(session, alias)
            except Exception:
                pass
            session.close()


class TestCrossDatabaseQueries:
    """Test cross-database query functionality."""

    def test_cross_database_query_example(self, populated_ioc_database_service):
        """Should perform cross-database queries as shown in docstring."""
        session = populated_ioc_database_service.session_local()
        try:
            # Attach IOC database
            populated_ioc_database_service.attach_to_session(session, "ioc")

            # Simulate the example query pattern (simplified without main detections table)
            result = session.execute(
                text("""
                SELECT s.scientific_name, s.english_name, t.common_name
                FROM ioc.species s
                LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name
                    AND t.language_code = :lang
                WHERE s.scientific_name = :species
            """),
                {"lang": "es", "species": "Turdus migratorius"},
            )

            row = result.fetchone()
            assert row is not None
            assert row[0] == "Turdus migratorius"  # scientific_name
            assert row[1] == "American Robin"  # english_name
            assert row[2] == "Petirrojo Americano"  # spanish translation

        finally:
            try:
                populated_ioc_database_service.detach_from_session(session, "ioc")
            except Exception:
                pass
            session.close()


class TestCreateIOCDatabaseFromFiles:
    """Test create_ioc_database_from_files function."""

    @patch("birdnetpi.services.ioc_database_service.IOCReferenceService")
    def test_create_ioc_database_from_files(
        self, mock_service_class, mock_ioc_reference_service, tmp_path
    ):
        """Should create database from XML and XLSX files."""
        xml_file = tmp_path / "test.xml"
        xlsx_file = tmp_path / "test.xlsx"
        db_path = str(tmp_path / "test.db")

        # Setup mock
        mock_service_class.return_value = mock_ioc_reference_service

        result = create_ioc_database_from_files(xml_file, xlsx_file, db_path)

        # Verify service was created and called correctly
        mock_service_class.assert_called_once()
        mock_ioc_reference_service.load_ioc_data.assert_called_once_with(
            xml_file=xml_file, xlsx_file=xlsx_file
        )

        # Verify returned service
        assert isinstance(result, IOCDatabaseService)
        assert result.db_path == db_path


class TestLanguageNameMapping:
    """Test language name mapping functionality."""

    def test_get_language_names_mapping(self, ioc_database_service):
        """Should provide comprehensive language name mapping."""
        language_names = ioc_database_service._get_language_names()

        # Test some key languages
        assert language_names["es"] == "Spanish"
        assert language_names["fr"] == "French"
        assert language_names["de"] == "German"
        assert language_names["zh"] == "Chinese"
        assert language_names["zh-TW"] == "Chinese (Traditional)"
        assert language_names["pt"] == "Portuguese"
        assert language_names["pt-PT"] == "Portuguese (Portuguese)"
        assert language_names["se"] == "Northern Sami"
        assert language_names["fr-Gaudin"] == "French (Gaudin)"

        # Verify comprehensive coverage
        assert len(language_names) >= 30  # Should have many language mappings


class TestErrorHandling:
    """Test error handling across the service."""

    def test_populate___invalid_service(self, ioc_database_service):
        """Should handle invalid service gracefully."""
        invalid_service = MagicMock()
        invalid_service._loaded = True
        invalid_service._species_data = "not a dict"  # Invalid data type

        with pytest.raises(RuntimeError):  # Will raise RuntimeError from the service
            ioc_database_service.populate_from_ioc_service(invalid_service)

    def test_session_handling_in_queries(self, populated_ioc_database_service):
        """Should properly handle sessions in all query methods."""
        # Test that sessions are properly closed even if queries fail
        from sqlalchemy.exc import SQLAlchemyError

        with patch.object(populated_ioc_database_service, "session_local") as mock_session_local:
            mock_session = MagicMock()
            mock_session.query.side_effect = SQLAlchemyError("Query error")
            mock_session_local.return_value = mock_session

            # These should all handle the exception and close the session
            with pytest.raises(SQLAlchemyError):
                populated_ioc_database_service.get_species_by_scientific_name("test")
            mock_session.close.assert_called()

            mock_session.reset_mock()
            with pytest.raises(SQLAlchemyError):
                populated_ioc_database_service.get_translation("test", "en")
            mock_session.close.assert_called()

            mock_session.reset_mock()
            with pytest.raises(SQLAlchemyError):
                populated_ioc_database_service.search_species_by_common_name("test")
            mock_session.close.assert_called()


class TestIntegration:
    """Integration tests for IOC database service."""

    def test_complete_workflow(self, ioc_database_service, mock_ioc_reference_service):
        """Should complete full workflow from service population to queries."""
        # Populate database
        ioc_database_service.populate_from_ioc_service(mock_ioc_reference_service)

        # Test species lookup
        species = ioc_database_service.get_species_by_scientific_name("Turdus migratorius")
        assert species is not None
        assert species.english_name == "American Robin"

        # Test translation lookup
        translation = ioc_database_service.get_translation("Turdus migratorius", "es")
        assert translation == "Petirrojo Americano"

        # Test search functionality
        search_results = ioc_database_service.search_species_by_common_name("Robin", "en")
        assert len(search_results) == 1
        assert search_results[0].scientific_name == "Turdus migratorius"

        # Test metadata retrieval
        metadata = ioc_database_service.get_metadata()
        assert metadata["ioc_version"] == "15.1"
        assert metadata["species_count"] == "2"

        # Test language metadata
        languages = ioc_database_service.get_available_languages()
        assert len(languages) == 3

        # Test database size
        size = ioc_database_service.get_database_size()
        assert size > 0

    def test_empty_database_behavior(self, ioc_database_service):
        """Should handle empty database gracefully."""
        # All queries should return empty/None results
        assert ioc_database_service.get_species_by_scientific_name("any") is None
        assert ioc_database_service.get_translation("any", "en") is None
        assert ioc_database_service.search_species_by_common_name("any") == []
        assert ioc_database_service.get_available_languages() == []
        assert ioc_database_service.get_metadata() == {}

        # Database size should be > 0 (schema exists)
        assert ioc_database_service.get_database_size() > 0
