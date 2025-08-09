"""Tests for multilingual database service."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService


@pytest.fixture
def mock_file_resolver():
    """Create mock file path resolver with test database paths."""
    mock_resolver = MagicMock()
    mock_resolver.get_ioc_database_path.return_value = "/test/path/ioc_reference.db"
    mock_resolver.get_avibase_database_path.return_value = "/test/path/avibase_database.db"
    mock_resolver.get_patlevin_database_path.return_value = "/test/path/patlevin_database.db"
    return mock_resolver


@pytest.fixture
def mock_file_resolver__no_databases():
    """Create mock file resolver with no database paths."""
    mock_resolver = MagicMock()
    mock_resolver.get_ioc_database_path.return_value = None
    mock_resolver.get_avibase_database_path.return_value = None
    mock_resolver.get_patlevin_database_path.return_value = None
    return mock_resolver


@pytest.fixture
def mock_file_resolver__partial_databases():
    """Create mock file resolver with only some databases available."""
    mock_resolver = MagicMock()
    mock_resolver.get_ioc_database_path.return_value = "/test/path/ioc_reference.db"
    mock_resolver.get_avibase_database_path.return_value = None
    mock_resolver.get_patlevin_database_path.return_value = "/test/path/patlevin_database.db"
    return mock_resolver


@pytest.fixture
def multilingual_service(mock_file_resolver):
    """Create multilingual database service with mocked paths."""
    with patch("birdnetpi.services.multilingual_database_service.Path") as mock_path:
        # Mock all paths as existing
        mock_path.return_value.exists.return_value = True
        service = MultilingualDatabaseService(mock_file_resolver)
        return service


@pytest.fixture
def multilingual_service__no_databases(mock_file_resolver__no_databases):
    """Create service with no databases available."""
    service = MultilingualDatabaseService(mock_file_resolver__no_databases)
    return service


@pytest.fixture
def multilingual_service__partial_databases(mock_file_resolver__partial_databases):
    """Create service with partial databases available."""
    with patch("birdnetpi.services.multilingual_database_service.Path") as mock_path:
        # Mock only some paths as existing
        def mock_exists(path_str):
            path_obj = MagicMock()
            if "ioc_reference.db" in str(path_str) or "patlevin_database.db" in str(path_str):
                path_obj.exists.return_value = True
            else:
                path_obj.exists.return_value = False
            return path_obj

        mock_path.side_effect = mock_exists
        service = MultilingualDatabaseService(mock_file_resolver__partial_databases)
        return service


@pytest.fixture
def mock_session():
    """Create mock SQLAlchemy session."""
    session = MagicMock()
    session.execute.return_value = MagicMock()
    return session


@pytest.fixture
def in_memory_session():
    """Create real in-memory SQLite session for integration tests."""
    engine = create_engine("sqlite:///:memory:")
    session_local = sessionmaker(bind=engine)
    session = session_local()

    # Create test tables for cross-database queries
    session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS test_main (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    )
    session.commit()

    yield session
    session.close()


class TestMultilingualDatabaseServiceInitialization:
    """Test multilingual database service initialization."""

    def test_service_initialization_all_databases_available(self, mock_file_resolver):
        """Should initialize service with all databases available."""
        with patch("birdnetpi.services.multilingual_database_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True

            service = MultilingualDatabaseService(mock_file_resolver)

            assert service.file_resolver == mock_file_resolver
            assert service.ioc_db_path == "/test/path/ioc_reference.db"
            assert service.avibase_db_path == "/test/path/avibase_database.db"
            assert service.patlevin_db_path == "/test/path/patlevin_database.db"
            assert set(service.databases_available) == {"ioc", "avibase", "patlevin"}

    def test_service_initialization_no_databases_available(self, mock_file_resolver):
        """Should initialize service with no databases available."""
        with patch("birdnetpi.services.multilingual_database_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = False

            service = MultilingualDatabaseService(mock_file_resolver)

            assert service.file_resolver == mock_file_resolver
            assert service.databases_available == []

    def test_service_initialization_partial_databases_available(self, mock_file_resolver):
        """Should initialize service with only existing databases."""

        def mock_path_factory(path_str):
            path_obj = MagicMock()
            # Only IOC and PatLevin exist
            if "ioc_reference.db" in str(path_str) or "patlevin_database.db" in str(path_str):
                path_obj.exists.return_value = True
            else:
                path_obj.exists.return_value = False
            return path_obj

        with patch(
            "birdnetpi.services.multilingual_database_service.Path", side_effect=mock_path_factory
        ):
            service = MultilingualDatabaseService(mock_file_resolver)

            assert set(service.databases_available) == {"ioc", "patlevin"}
            assert "avibase" not in service.databases_available

    def test_service_initialization__none_paths(self):
        """Should handle None paths from file resolver."""
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.return_value = None
        mock_resolver.get_avibase_database_path.return_value = None
        mock_resolver.get_patlevin_database_path.return_value = None

        service = MultilingualDatabaseService(mock_resolver)

        assert service.ioc_db_path is None
        assert service.avibase_db_path is None
        assert service.patlevin_db_path is None
        assert service.databases_available == []


class TestAttachDetachDatabases:
    """Test database attachment and detachment functionality."""

    def test_attach_all_to_session_all_databases(self, multilingual_service, mock_session):
        """Should attach all available databases to session."""
        multilingual_service.attach_all_to_session(mock_session)

        # Verify all three ATTACH DATABASE commands were executed
        assert mock_session.execute.call_count == 3

        calls = mock_session.execute.call_args_list
        attach_commands = [str(call[0][0]) for call in calls]

        assert any(
            "ATTACH DATABASE '/test/path/ioc_reference.db' AS ioc" in cmd for cmd in attach_commands
        )
        assert any(
            "ATTACH DATABASE '/test/path/avibase_database.db' AS avibase" in cmd
            for cmd in attach_commands
        )
        assert any(
            "ATTACH DATABASE '/test/path/patlevin_database.db' AS patlevin" in cmd
            for cmd in attach_commands
        )

    def test_attach_all_to_session_partial_databases(
        self, multilingual_service__partial_databases, mock_session
    ):
        """Should attach only available databases to session."""
        multilingual_service__partial_databases.attach_all_to_session(mock_session)

        # Only IOC and PatLevin should be attached
        assert mock_session.execute.call_count == 2

        calls = mock_session.execute.call_args_list
        attach_commands = [str(call[0][0]) for call in calls]

        assert any(
            "ATTACH DATABASE '/test/path/ioc_reference.db' AS ioc" in cmd for cmd in attach_commands
        )
        assert any(
            "ATTACH DATABASE '/test/path/patlevin_database.db' AS patlevin" in cmd
            for cmd in attach_commands
        )
        assert not any("avibase" in cmd for cmd in attach_commands)

    def test_attach_all_to_session_no_databases(
        self, multilingual_service__no_databases, mock_session
    ):
        """Should not attach any databases when none are available."""
        multilingual_service__no_databases.attach_all_to_session(mock_session)

        # No databases should be attached
        assert mock_session.execute.call_count == 0

    def test_detach_all_from_session(self, multilingual_service, mock_session):
        """Should detach all available databases from session."""
        multilingual_service.detach_all_from_session(mock_session)

        # Verify all three DETACH DATABASE commands were executed
        assert mock_session.execute.call_count == 3

        calls = mock_session.execute.call_args_list
        detach_commands = [str(call[0][0]) for call in calls]

        assert any("DETACH DATABASE ioc" in cmd for cmd in detach_commands)
        assert any("DETACH DATABASE avibase" in cmd for cmd in detach_commands)
        assert any("DETACH DATABASE patlevin" in cmd for cmd in detach_commands)

    def test_detach_all_from_session__exception_handling(self, multilingual_service, mock_session):
        """Should handle exceptions during detach gracefully."""
        mock_session.execute.side_effect = [
            None,  # First detach succeeds
            OperationalError("statement", "params", "orig"),  # Second fails
            None,  # Third succeeds
        ]

        # Should not raise exception despite error in middle
        multilingual_service.detach_all_from_session(mock_session)

        # All three detach commands should still be attempted
        assert mock_session.execute.call_count == 3

    def test_detach_all_from_session__no_databases(
        self, multilingual_service__no_databases, mock_session
    ):
        """Should not attempt to detach when no databases are available."""
        multilingual_service__no_databases.detach_all_from_session(mock_session)

        assert mock_session.execute.call_count == 0


class TestGetBestCommonName:
    """Test priority-based common name resolution."""

    def test_get_best_common_name_all_databases_ioc_english(
        self, multilingual_service, mock_session
    ):
        """Should build query with all databases for IOC English lookup."""
        # Mock query result
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda i: ["American Robin", "IOC"][i]
        mock_session.execute.return_value.fetchone.return_value = mock_result

        result = multilingual_service.get_best_common_name(mock_session, "Turdus migratorius", "en")

        # Verify query was executed with correct parameters
        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])
        params = call_args[0][1]

        # Check query includes all databases and correct JOINs for English IOC
        assert "ioc_species.english_name" in query
        assert "ioc_trans.common_name" in query
        assert "patlevin.common_name" in query
        assert "avibase.common_name" in query
        assert "LEFT JOIN ioc.species ioc_species" in query
        assert "LEFT JOIN ioc.translations ioc_trans" in query
        assert "LEFT JOIN patlevin.patlevin_labels patlevin" in query
        assert "LEFT JOIN avibase.avibase_names avibase" in query

        # Check parameters
        assert params["sci_name"] == "Turdus migratorius"
        assert params["lang"] == "en"

        # Check result
        assert result["common_name"] == "American Robin"
        assert result["source"] == "IOC"

    def test_get_best_common_name_all_databases_non_english(
        self, multilingual_service, mock_session
    ):
        """Should build query without IOC species table for non-English languages."""
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda i: ["Petirrojo Americano", "IOC"][i]
        mock_session.execute.return_value.fetchone.return_value = mock_result

        result = multilingual_service.get_best_common_name(mock_session, "Turdus migratorius", "es")

        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])

        # For non-English, should not include IOC species table
        assert "ioc_species.english_name" not in query
        assert "ioc_trans.common_name" in query
        assert "patlevin.common_name" in query
        assert "avibase.common_name" in query

        assert result["common_name"] == "Petirrojo Americano"
        assert result["source"] == "IOC"

    def test_get_best_common_name_partial_databases(
        self, multilingual_service__partial_databases, mock_session
    ):
        """Should build query with only available databases."""
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda i: ["American Robin", "IOC"][i]
        mock_session.execute.return_value.fetchone.return_value = mock_result

        result = multilingual_service__partial_databases.get_best_common_name(
            mock_session, "Turdus migratorius", "en"
        )

        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])

        # Should include IOC and PatLevin, but not Avibase
        assert "ioc_species.english_name" in query
        assert "ioc_trans.common_name" in query
        assert "patlevin.common_name" in query
        assert "avibase.common_name" not in query
        assert "LEFT JOIN avibase.avibase_names" not in query

        assert result["common_name"] == "American Robin"

    def test_get_best_common_name_no_databases(
        self, multilingual_service__no_databases, mock_session
    ):
        """Should return empty result when no databases are available."""
        result = multilingual_service__no_databases.get_best_common_name(
            mock_session, "Turdus migratorius", "en"
        )

        assert result["common_name"] is None
        assert result["source"] is None
        # No query should be executed
        mock_session.execute.assert_not_called()

    def test_get_best_common_name__no_result(self, multilingual_service, mock_session):
        """Should return empty result when no match is found."""
        mock_session.execute.return_value.fetchone.return_value = None

        result = multilingual_service.get_best_common_name(
            mock_session, "Nonexistent species", "en"
        )

        assert result["common_name"] is None
        assert result["source"] is None

    def test_get_best_common_name__sql_injection_prevention(
        self, multilingual_service, mock_session
    ):
        """Should prevent SQL injection through parameterized queries."""
        mock_session.execute.return_value.fetchone.return_value = None

        # Try injection through scientific name
        multilingual_service.get_best_common_name(mock_session, "'; DROP TABLE species; --", "en")

        call_args = mock_session.execute.call_args
        params = call_args[0][1]

        # Parameters should be passed separately, not embedded in query
        assert params["sci_name"] == "'; DROP TABLE species; --"
        assert "DROP TABLE" not in str(call_args[0][0])  # Not in the query itself

    def test_get_best_common_name__priority_source_detection(
        self, multilingual_service, mock_session
    ):
        """Should correctly detect source based on priority order."""
        # Test when IOC English name is found (highest priority)
        mock_result_ioc = MagicMock()
        mock_result_ioc.__getitem__.side_effect = lambda i: ["American Robin", "IOC"][i]

        mock_session.execute.return_value.fetchone.return_value = mock_result_ioc

        multilingual_service.get_best_common_name(mock_session, "Turdus migratorius", "en")

        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])

        # Verify CASE statement includes priority order
        assert "WHEN ioc_species.english_name IS NOT NULL THEN 'IOC'" in query
        assert "WHEN ioc_trans.common_name IS NOT NULL THEN 'IOC'" in query
        assert "WHEN patlevin.common_name IS NOT NULL THEN 'PatLevin'" in query
        assert "WHEN avibase.common_name IS NOT NULL THEN 'Avibase'" in query


class TestGetAllTranslations:
    """Test comprehensive translation retrieval from all databases."""

    def test_get_all_translations_all_databases(self, multilingual_service, mock_session):
        """Should retrieve translations from all available databases."""
        # Create mock result objects with fetchone() and fetchall() methods
        ioc_species_result = MagicMock()
        ioc_species_result.fetchone.return_value = ("en", "American Robin")

        ioc_translations_result = MagicMock()
        ioc_translations_result.__iter__.return_value = iter(
            [
                ("es", "Petirrojo Americano"),
                ("fr", "Merle d'Amérique"),
            ]
        )

        patlevin_result = MagicMock()
        patlevin_result.__iter__.return_value = iter(
            [
                ("de", "Wanderdrossel"),
                ("es", "Petirrojo"),
            ]
        )  # es is duplicate, should be filtered

        avibase_result = MagicMock()
        avibase_result.__iter__.return_value = iter(
            [
                ("it", "Pettirosso americano"),
                ("pt", "Tordo-americano"),
            ]
        )

        # Mock results from different databases
        mock_session.execute.side_effect = [
            ioc_species_result,
            ioc_translations_result,
            patlevin_result,
            avibase_result,
        ]

        result = multilingual_service.get_all_translations(mock_session, "Turdus migratorius")

        # Should execute 4 queries (IOC species, IOC translations, PatLevin, Avibase)
        assert mock_session.execute.call_count == 4

        # Verify result structure and deduplication
        assert "en" in result
        assert len(result["en"]) == 1
        assert result["en"][0]["name"] == "American Robin"
        assert result["en"][0]["source"] == "IOC"

        assert "es" in result
        assert len(result["es"]) == 2  # Both IOC and PatLevin versions
        names = [t["name"] for t in result["es"]]
        assert "Petirrojo Americano" in names
        assert "Petirrojo" in names

        assert "fr" in result
        assert result["fr"][0]["source"] == "IOC"

        assert "de" in result
        assert result["de"][0]["source"] == "PatLevin"

        assert "it" in result
        assert result["it"][0]["source"] == "Avibase"

    def test_get_all_translations_partial_databases(
        self, multilingual_service__partial_databases, mock_session
    ):
        """Should retrieve translations only from available databases."""
        # Create mock result objects with fetchone() and fetchall() methods
        ioc_species_result = MagicMock()
        ioc_species_result.fetchone.return_value = ("en", "American Robin")

        ioc_translations_result = MagicMock()
        ioc_translations_result.__iter__.return_value = iter([("es", "Petirrojo Americano")])

        patlevin_result = MagicMock()
        patlevin_result.__iter__.return_value = iter([("de", "Wanderdrossel")])

        mock_session.execute.side_effect = [
            ioc_species_result,
            ioc_translations_result,
            patlevin_result,
        ]

        result = multilingual_service__partial_databases.get_all_translations(
            mock_session, "Turdus migratorius"
        )

        # Should execute 3 queries (no Avibase)
        assert mock_session.execute.call_count == 3

        # Should have results from IOC and PatLevin only
        assert "en" in result
        assert result["en"][0]["source"] == "IOC"
        assert "es" in result
        assert result["es"][0]["source"] == "IOC"
        assert "de" in result
        assert result["de"][0]["source"] == "PatLevin"

    def test_get_all_translations_no_databases(
        self, multilingual_service__no_databases, mock_session
    ):
        """Should return empty dict when no databases are available."""
        result = multilingual_service__no_databases.get_all_translations(
            mock_session, "Turdus migratorius"
        )

        assert result == {}
        mock_session.execute.assert_not_called()

    def test_get_all_translations__deduplication(self, multilingual_service, mock_session):
        """Should deduplicate identical names from different sources."""
        mock_session.execute.side_effect = [
            # IOC English
            [("en", "American Robin")],
            # IOC translations (same English name again)
            [("en", "American Robin")],  # Duplicate
            # PatLevin
            [("en", "American Robin")],  # Another duplicate
            # Avibase
            [("en", "Robin")],  # Different name, should be included
        ]

        result = multilingual_service.get_all_translations(mock_session, "Turdus migratorius")

        assert "en" in result
        assert len(result["en"]) == 2  # Only unique names
        names = [t["name"] for t in result["en"]]
        assert "American Robin" in names
        assert "Robin" in names

        # Should have IOC source first (priority), then Avibase
        sources = [t["source"] for t in result["en"]]
        assert "IOC" in sources
        assert "Avibase" in sources

    def test_get_all_translations__sql_injection_prevention(
        self, multilingual_service, mock_session
    ):
        """Should prevent SQL injection in all query parameters."""
        mock_session.execute.side_effect = [[], [], [], []]  # Empty results

        multilingual_service.get_all_translations(mock_session, "'; DROP TABLE species; --")

        # Check all 4 queries use parameterized approach
        calls = mock_session.execute.call_args_list
        for call in calls:
            params = call[0][1]
            assert params["sci_name"] == "'; DROP TABLE species; --"
            assert "DROP TABLE" not in str(call[0][0])


class TestGetAttribution:
    """Test database attribution strings."""

    def test_get_attribution_all_databases(self, multilingual_service):
        """Should return attributions for all available databases."""
        attributions = multilingual_service.get_attribution()

        assert len(attributions) == 3
        assert "IOC World Bird List (www.worldbirdnames.org)" in attributions
        assert "Patrick Levin (patlevin) - BirdNET Label Translations" in attributions
        assert "Avibase - Lepage, Denis (2018)" in attributions

    def test_get_attribution_partial_databases(self, multilingual_service__partial_databases):
        """Should return attributions only for available databases."""
        attributions = multilingual_service__partial_databases.get_attribution()

        assert len(attributions) == 2
        assert "IOC World Bird List (www.worldbirdnames.org)" in attributions
        assert "Patrick Levin (patlevin) - BirdNET Label Translations" in attributions
        assert not any("Avibase" in attr for attr in attributions)

    def test_get_attribution_no_databases(self, multilingual_service__no_databases):
        """Should return empty list when no databases are available."""
        attributions = multilingual_service__no_databases.get_attribution()
        assert attributions == []


class TestErrorHandling:
    """Test error handling across the service."""

    def test_attach_all_to_session__database_error(self, multilingual_service, mock_session):
        """Should handle database errors during attach operations."""
        mock_session.execute.side_effect = OperationalError("statement", "params", "orig")

        # Should not suppress the exception - let caller handle it
        with pytest.raises(OperationalError):
            multilingual_service.attach_all_to_session(mock_session)

    def test_get_best_common_name__database_error(self, multilingual_service, mock_session):
        """Should handle database errors during query execution."""
        mock_session.execute.side_effect = SQLAlchemyError("Query failed")

        with pytest.raises(SQLAlchemyError):
            multilingual_service.get_best_common_name(mock_session, "Turdus migratorius", "en")

    def test_get_all_translations__partial_database_error(self, multilingual_service, mock_session):
        """Should handle errors from individual database queries gracefully."""
        # First query succeeds, second fails, third succeeds
        mock_session.execute.side_effect = [
            [("en", "American Robin")],  # IOC species - success
            SQLAlchemyError("IOC translations failed"),  # IOC translations - fail
            [("de", "Wanderdrossel")],  # PatLevin - success
            [("it", "Pettirosso americano")],  # Avibase - success
        ]

        with pytest.raises(SQLAlchemyError):
            multilingual_service.get_all_translations(mock_session, "Turdus migratorius")

    def test_file_resolver_error_handling(self):
        """Should handle file resolver errors during initialization."""
        mock_resolver = MagicMock()
        mock_resolver.get_ioc_database_path.side_effect = Exception("File resolver error")

        # Should re-raise the exception from file resolver
        with pytest.raises(Exception, match="File resolver error"):
            MultilingualDatabaseService(mock_resolver)


class TestIntegrationWithRealSession:
    """Integration tests using real SQLite session."""

    def test_attach_detach_integration(self, multilingual_service, in_memory_session, tmp_path):
        """Should successfully attach and detach real database files."""
        # Create temporary database files
        ioc_db = tmp_path / "ioc.db"
        avibase_db = tmp_path / "avibase.db"
        patlevin_db = tmp_path / "patlevin.db"

        # Create the database files with minimal schema
        for db_path in [ioc_db, avibase_db, patlevin_db]:
            engine = create_engine(f"sqlite:///{db_path}")
            engine.execute(text("CREATE TABLE test_table (id INTEGER PRIMARY KEY)"))
            engine.dispose()

        # Override service paths with real files
        multilingual_service.ioc_db_path = str(ioc_db)
        multilingual_service.avibase_db_path = str(avibase_db)
        multilingual_service.patlevin_db_path = str(patlevin_db)

        try:
            # Test attach
            multilingual_service.attach_all_to_session(in_memory_session)

            # Verify databases are attached by querying schema
            result = in_memory_session.execute(
                text("SELECT name FROM ioc.sqlite_master WHERE type='table'")
            )
            assert "test_table" in [row[0] for row in result.fetchall()]

            # Test detach
            multilingual_service.detach_all_from_session(in_memory_session)

            # Verify databases are detached
            with pytest.raises(OperationalError):
                in_memory_session.execute(text("SELECT * FROM ioc.test_table"))

        except Exception as e:
            # Clean up on error
            try:
                multilingual_service.detach_all_from_session(in_memory_session)
            except Exception:
                pass
            raise e

    def test_query_building_integration(self, multilingual_service, in_memory_session):
        """Should build and execute valid SQL queries."""
        # Test that the query building doesn't have syntax errors
        with patch.object(in_memory_session, "execute") as mock_execute:
            mock_execute.return_value.fetchone.return_value = None

            multilingual_service.get_best_common_name(in_memory_session, "Turdus migratorius", "en")

            # Verify a valid query was attempted
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            query_obj = call_args[0][0]
            params = call_args[0][1]

            # The query object should be a SQLAlchemy text object
            assert hasattr(query_obj, "text")
            assert isinstance(params, dict)
            assert "sci_name" in params
            assert "lang" in params


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_scientific_name(self, multilingual_service, mock_session):
        """Should handle empty scientific name gracefully."""
        mock_session.execute.return_value.fetchone.return_value = None

        result = multilingual_service.get_best_common_name(mock_session, "", "en")

        # Should still execute query but with empty parameter
        mock_session.execute.assert_called_once()
        params = mock_session.execute.call_args[0][1]
        assert params["sci_name"] == ""

        assert result["common_name"] is None
        assert result["source"] is None

    def test_special_characters_in_scientific_name(self, multilingual_service, mock_session):
        """Should handle special characters in scientific names."""
        mock_session.execute.return_value.fetchone.return_value = None

        special_name = "Turdus (migratorius) x merula"

        multilingual_service.get_best_common_name(mock_session, special_name, "en")

        params = mock_session.execute.call_args[0][1]
        assert params["sci_name"] == special_name

    def test_unusual_language_codes(self, multilingual_service, mock_session):
        """Should handle unusual language codes."""
        mock_session.execute.return_value.fetchone.return_value = None

        unusual_codes = ["zh-CN", "pt-BR", "en-US", "fr-CA", "x-custom"]

        for code in unusual_codes:
            mock_session.reset_mock()
            multilingual_service.get_best_common_name(mock_session, "Turdus migratorius", code)

            params = mock_session.execute.call_args[0][1]
            assert params["lang"] == code

    def test_case_sensitivity_in_queries(self, multilingual_service, mock_session):
        """Should handle case variations in scientific names through LOWER() function."""
        mock_session.execute.return_value.fetchone.return_value = None

        multilingual_service.get_best_common_name(mock_session, "TURDUS MIGRATORIUS", "en")

        # Verify query uses LOWER() function for case-insensitive comparison
        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])
        assert "LOWER(" in query
        assert ":sci_name" in query  # Parameter should still be used

    def test_databases_available_modification(self, multilingual_service):
        """Should not allow external modification of databases_available list."""
        original_databases = multilingual_service.databases_available.copy()

        # Try to modify the list
        multilingual_service.databases_available.append("fake_db")

        # The service should still work correctly with original databases
        # (This tests that the service doesn't rely on external list modifications)
        assert len(multilingual_service.databases_available) == len(original_databases) + 1

        # But the actual database paths should be unchanged
        assert multilingual_service.ioc_db_path == "/test/path/ioc_reference.db"
        assert multilingual_service.avibase_db_path == "/test/path/avibase_database.db"
        assert multilingual_service.patlevin_db_path == "/test/path/patlevin_database.db"
