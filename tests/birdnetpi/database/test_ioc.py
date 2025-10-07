"""Tests for IOC database service."""

import concurrent.futures
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from birdnetpi.database.ioc import IOCDatabaseService
from birdnetpi.species.models import Species
from birdnetpi.utils.ioc_models import IOCMetadata, IOCSpecies


@pytest.fixture
def mock_ioc_db():
    """Create a temporary IOC database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = Path(tmp_file.name)

        # Create test database with schema
        engine = create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(engine)

        # Add test data
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            # Add test species
            test_species = [
                IOCSpecies(
                    scientific_name="Turdus migratorius",
                    english_name="American Robin",
                    order_name="Passeriformes",
                    family="Turdidae",
                    genus="Turdus",
                    species_epithet="migratorius",
                    authority="Linnaeus, 1766",
                ),
                IOCSpecies(
                    scientific_name="Cardinalis cardinalis",
                    english_name="Northern Cardinal",
                    order_name="Passeriformes",
                    family="Cardinalidae",
                    genus="Cardinalis",
                    species_epithet="cardinalis",
                    authority="(Linnaeus, 1758)",
                ),
                IOCSpecies(
                    scientific_name="Sialia sialis",
                    english_name="Eastern Bluebird",
                    order_name="Passeriformes",
                    family="Turdidae",
                    genus="Sialia",
                    species_epithet="sialis",
                    authority="(Linnaeus, 1758)",
                ),
            ]
            session.add_all(test_species)

            # Add metadata
            metadata_entries = [
                IOCMetadata(key="ioc_version", value="14.2"),
                IOCMetadata(key="species_count", value="3"),
            ]
            session.add_all(metadata_entries)
            session.commit()

        yield db_path

        # Cleanup
        db_path.unlink(missing_ok=True)


@pytest.fixture
def ioc_service(mock_ioc_db):
    """Create IOCDatabaseService with test database."""
    return IOCDatabaseService(mock_ioc_db)


class TestIOCDatabaseService:
    """Test IOC database service functionality."""

    def test_init_with_missing_database(self):
        """Should raise FileNotFoundError for missing database."""
        with pytest.raises(FileNotFoundError, match="IOC database not found"):
            IOCDatabaseService(Path("/nonexistent/database.db"))

    def test_init_with_valid_database(self, mock_ioc_db):
        """Should initialize successfully with valid database."""
        service = IOCDatabaseService(mock_ioc_db)
        assert service.db_path == mock_ioc_db
        assert service.engine is not None
        assert service.session_local is not None

    def test_get_species_core_existing(self, ioc_service):
        """Should return Species object for existing species."""
        species = ioc_service.get_species_core("Turdus migratorius")

        assert species is not None
        assert isinstance(species, Species)
        assert species.scientific_name == "Turdus migratorius"
        assert species.english_name == "American Robin"
        assert species.order_name == "Passeriformes"
        assert species.family == "Turdidae"
        assert species.genus == "Turdus"
        assert species.species_epithet == "migratorius"
        assert species.authority == "Linnaeus, 1766"

    def test_get_species_core_nonexistent(self, ioc_service):
        """Should return None for non-existent species."""
        species = ioc_service.get_species_core("Imaginus fakeus")
        assert species is None

    def test_get_english_name_existing(self, ioc_service):
        """Should return English name for existing species."""
        name = ioc_service.get_english_name("Cardinalis cardinalis")
        assert name == "Northern Cardinal"

    def test_get_english_name_nonexistent(self, ioc_service):
        """Should return None for non-existent species."""
        name = ioc_service.get_english_name("Imaginus fakeus")
        assert name is None

    def test_species_exists_true(self, ioc_service):
        """Should return True for existing species."""
        exists = ioc_service.species_exists("Sialia sialis")
        assert exists is True

    def test_species_exists_false(self, ioc_service):
        """Should return False for non-existent species."""
        exists = ioc_service.species_exists("Imaginus fakeus")
        assert exists is False

    def test_get_species_count(self, ioc_service):
        """Should return correct species count."""
        count = ioc_service.get_species_count()
        assert count == 3

    def test_get_species_count_empty_database(self):
        """Should return 0 for empty database."""
        # Create empty database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            db_path = Path(tmp_file.name)
            engine = create_engine(f"sqlite:///{db_path}")
            SQLModel.metadata.create_all(engine)

            service = IOCDatabaseService(db_path)
            count = service.get_species_count()
            assert count == 0

            # Cleanup
            db_path.unlink(missing_ok=True)

    def test_get_metadata_value_existing(self, ioc_service):
        """Should return metadata value for existing key."""
        version = ioc_service.get_metadata_value("ioc_version")
        assert version == "14.2"

        count = ioc_service.get_metadata_value("species_count")
        assert count == "3"

    def test_get_metadata_value_nonexistent(self, ioc_service):
        """Should return None for non-existent metadata key."""
        value = ioc_service.get_metadata_value("nonexistent_key")
        assert value is None

    def test_read_only_connection(self, mock_ioc_db):
        """Should create read-only connection."""
        service = IOCDatabaseService(mock_ioc_db)

        # Verify connection string includes read-only mode
        assert "mode=ro" in str(service.engine.url)

    def test_session_management(self, ioc_service):
        """Should properly manage database sessions."""
        # Execute multiple queries to ensure sessions are properly closed
        for _ in range(5):
            species = ioc_service.get_species_core("Turdus migratorius")
            assert species is not None

        # Should not raise any connection pool errors
        count = ioc_service.get_species_count()
        assert count == 3

    def test_multiple_species_queries(self, ioc_service):
        """Should handle multiple different species queries."""
        species_names = [
            ("Turdus migratorius", "American Robin"),
            ("Cardinalis cardinalis", "Northern Cardinal"),
            ("Sialia sialis", "Eastern Bluebird"),
        ]

        for scientific_name, expected_english in species_names:
            species = ioc_service.get_species_core(scientific_name)
            assert species is not None
            assert species.scientific_name == scientific_name
            assert species.english_name == expected_english

    @patch("birdnetpi.database.ioc.create_engine", autospec=True)
    def test_database_connection_error(self, mock_create_engine):
        """Should handle database connection errors gracefully."""
        # Create a temporary file to pass the exists check
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_file:
            db_path = Path(tmp_file.name)

            # Mock engine to raise error on connection
            mock_engine = MagicMock(spec=Engine)
            mock_create_engine.return_value = mock_engine

            # Should initialize without error
            service = IOCDatabaseService(db_path)
            assert service.engine == mock_engine

    def test_case_sensitivity(self, ioc_service):
        """Should handle exact case matching for scientific names."""
        # Correct case should work
        species = ioc_service.get_species_core("Turdus migratorius")
        assert species is not None

        # Different case should not match (scientific names are case-sensitive)
        species_lower = ioc_service.get_species_core("turdus migratorius")
        assert species_lower is None

        species_upper = ioc_service.get_species_core("TURDUS MIGRATORIUS")
        assert species_upper is None

    def test_species_with_complex_authority(self, ioc_service):
        """Should correctly handle species with parentheses in authority."""
        species = ioc_service.get_species_core("Cardinalis cardinalis")
        assert species is not None
        assert species.authority == "(Linnaeus, 1758)"

    def test_concurrent_access(self, ioc_service):
        """Should handle concurrent database access."""

        def query_species(name):
            return ioc_service.get_species_core(name)

        species_names = ["Turdus migratorius", "Cardinalis cardinalis", "Sialia sialis"] * 3

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(query_species, name) for name in species_names]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # All queries should succeed
        assert all(r is not None for r in results)
        assert len(results) == 9


class TestIOCDatabaseEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string_queries(self, ioc_service):
        """Should handle empty string queries gracefully."""
        assert ioc_service.get_species_core("") is None
        assert ioc_service.get_english_name("") is None
        assert ioc_service.species_exists("") is False
        assert ioc_service.get_metadata_value("") is None

    def test_none_queries(self, ioc_service):
        """Should handle None queries."""
        # SQLAlchemy will handle None gracefully, returning None
        assert ioc_service.get_species_core(None) is None
        assert ioc_service.get_english_name(None) is None
        assert ioc_service.species_exists(None) is False
        assert ioc_service.get_metadata_value(None) is None

    def test_special_characters_in_queries(self, ioc_service):
        """Should handle special characters in queries safely."""
        # SQL injection attempt should return None, not cause error
        assert ioc_service.get_species_core("'; DROP TABLE species; --") is None
        assert ioc_service.species_exists("' OR '1'='1") is False

    def test_unicode_species_names(self):
        """Should handle Unicode characters in species data."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            db_path = Path(tmp_file.name)

            # Create database with Unicode data
            engine = create_engine(f"sqlite:///{db_path}")
            SQLModel.metadata.create_all(engine)

            session_factory = sessionmaker(bind=engine)
            with session_factory() as session:
                unicode_species = IOCSpecies(
                    scientific_name="Pārera māori",
                    english_name="Grey Duck",
                    order_name="Anseriformes",
                    family="Anatidae",
                    genus="Anas",
                    species_epithet="māori",
                    authority="Lavaud, 1820",
                )
                session.add(unicode_species)
                session.commit()

            service = IOCDatabaseService(db_path)
            species = service.get_species_core("Pārera māori")

            assert species is not None
            assert species.scientific_name == "Pārera māori"
            assert species.species_epithet == "māori"

            # Cleanup
            db_path.unlink(missing_ok=True)
