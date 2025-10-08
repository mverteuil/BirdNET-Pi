"""Tests for IOC database service - Refactored with parameterization."""

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

    @pytest.mark.parametrize(
        "scientific_name, expected_english, expected_exists",
        [
            pytest.param(
                "Turdus migratorius",
                "American Robin",
                True,
                id="american-robin-exists",
            ),
            pytest.param(
                "Cardinalis cardinalis",
                "Northern Cardinal",
                True,
                id="northern-cardinal-exists",
            ),
            pytest.param(
                "Sialia sialis",
                "Eastern Bluebird",
                True,
                id="eastern-bluebird-exists",
            ),
            pytest.param(
                "Imaginus fakeus",
                None,
                False,
                id="nonexistent-species",
            ),
        ],
    )
    def test_species_queries(self, ioc_service, scientific_name, expected_english, expected_exists):
        """Should handle species queries for existing and non-existing species."""
        # Test get_species_core
        species = ioc_service.get_species_core(scientific_name)
        if expected_exists:
            assert species is not None
            assert isinstance(species, Species)
            assert species.scientific_name == scientific_name
            assert species.english_name == expected_english
        else:
            assert species is None

        # Test get_english_name
        name = ioc_service.get_english_name(scientific_name)
        assert name == expected_english

        # Test species_exists
        exists = ioc_service.species_exists(scientific_name)
        assert exists is expected_exists

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

    @pytest.mark.parametrize(
        "metadata_key, expected_value",
        [
            pytest.param("ioc_version", "14.2", id="ioc-version"),
            pytest.param("species_count", "3", id="species-count"),
            pytest.param("nonexistent_key", None, id="nonexistent-key"),
        ],
    )
    def test_get_metadata_value(self, ioc_service, metadata_key, expected_value):
        """Should return metadata values for existing and non-existing keys."""
        value = ioc_service.get_metadata_value(metadata_key)
        assert value == expected_value

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

    @pytest.mark.parametrize(
        "scientific_name, expected_english",
        [
            ("Turdus migratorius", "American Robin"),
            ("Cardinalis cardinalis", "Northern Cardinal"),
            ("Sialia sialis", "Eastern Bluebird"),
        ],
        ids=["robin", "cardinal", "bluebird"],
    )
    def test_multiple_species_queries(self, ioc_service, scientific_name, expected_english):
        """Should handle multiple different species queries."""
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

    @pytest.mark.parametrize(
        "input_name, should_match",
        [
            pytest.param("Turdus migratorius", True, id="correct-case"),
            pytest.param("turdus migratorius", False, id="lowercase"),
            pytest.param("TURDUS MIGRATORIUS", False, id="uppercase"),
        ],
    )
    def test_case_sensitivity(self, ioc_service, input_name, should_match):
        """Should handle exact case matching for scientific names."""
        species = ioc_service.get_species_core(input_name)
        if should_match:
            assert species is not None
        else:
            assert species is None

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

    @pytest.mark.parametrize(
        "query_input, method_name",
        [
            pytest.param("", "get_species_core", id="empty-species"),
            pytest.param("", "get_english_name", id="empty-english"),
            pytest.param("", "species_exists", id="empty-exists"),
            pytest.param("", "get_metadata_value", id="empty-metadata"),
            pytest.param(None, "get_species_core", id="none-species"),
            pytest.param(None, "get_english_name", id="none-english"),
            pytest.param(None, "species_exists", id="none-exists"),
            pytest.param(None, "get_metadata_value", id="none-metadata"),
        ],
    )
    def test_invalid_queries(self, ioc_service, query_input, method_name):
        """Should handle empty string and None queries gracefully."""
        method = getattr(ioc_service, method_name)
        result = method(query_input)

        # All methods should return None or False for invalid input
        if method_name == "species_exists":
            assert result is False
        else:
            assert result is None

    @pytest.mark.parametrize(
        "malicious_input",
        [
            pytest.param("'; DROP TABLE species; --", id="sql-drop-table"),
            pytest.param("' OR '1'='1", id="sql-or-injection"),
            pytest.param("'; SELECT * FROM species; --", id="sql-select"),
        ],
    )
    def test_sql_injection_prevention(self, ioc_service, malicious_input):
        """Should handle SQL injection attempts safely."""
        # These should all return None/False, not cause errors or succeed
        assert ioc_service.get_species_core(malicious_input) is None
        assert ioc_service.get_english_name(malicious_input) is None
        assert ioc_service.species_exists(malicious_input) is False
        assert ioc_service.get_metadata_value(malicious_input) is None

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
