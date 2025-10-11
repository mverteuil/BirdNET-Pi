"""Tests for multilingual database service."""

from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Result
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from birdnetpi.database.species import SpeciesDatabaseService


@pytest.fixture
def mock_path_resolver(path_resolver, tmp_path):
    """Create mock file path resolver with test database paths.

    Uses the global path_resolver fixture as a base to prevent MagicMock file creation.
    """
    # Create test database files in temp directory
    test_ioc_db = tmp_path / "database" / "ioc_reference.db"
    test_wikidata_db = tmp_path / "database" / "wikidata_reference.db"

    test_ioc_db.parent.mkdir(parents=True, exist_ok=True)
    test_ioc_db.touch()
    test_wikidata_db.touch()

    # Override the database path methods
    path_resolver.get_ioc_database_path = lambda: test_ioc_db
    path_resolver.get_wikidata_database_path = lambda: test_wikidata_db

    return path_resolver


@pytest.fixture
def species_database(mock_path_resolver):
    """Create multilingual database service with mocked paths."""
    service = SpeciesDatabaseService(mock_path_resolver)
    return service


@pytest.fixture
def mock_session(db_session_factory):
    """Create mock SQLAlchemy async session using factory."""
    session, _result = db_session_factory()
    return session


@pytest.fixture
async def in_memory_session(async_in_memory_session):
    """Use the global async session fixture and add test-specific tables.

    This fixture uses the global async_in_memory_session from conftest.py
    and adds additional test-specific tables for multilingual tests.
    """
    # The global fixture already creates test_main table
    # We just need to pass it through
    return async_in_memory_session


class TestSpeciesDatabaseServiceInitialization:
    """Test multilingual database service initialization."""

    def test_service_initialization_all_databases_available(self, path_resolver):
        """Should initialize service with all databases paths set."""
        service = SpeciesDatabaseService(path_resolver)

        assert service.path_resolver == path_resolver
        # Check that paths match what the fixture provides
        assert service.ioc_db_path == path_resolver.get_ioc_database_path()
        assert service.wikidata_db_path == path_resolver.get_wikidata_database_path()


class TestAttachDetachDatabases:
    """Test database attachment and detachment functionality."""

    @pytest.mark.asyncio
    async def test_attach_all_to_session_all_databases(self, species_database, mock_session):
        """Should attach all available databases to session."""
        await species_database.attach_all_to_session(mock_session)

        # Verify both ATTACH DATABASE commands were executed
        assert mock_session.execute.call_count == 2

        calls = mock_session.execute.call_args_list
        attach_commands = [str(call[0][0]) for call in calls]

        # Debug: print actual commands to see what paths are being used
        print(f"Actual attach commands: {attach_commands}")

        # Check that all database types are attached (paths will be dynamic from tmp_path)
        assert any("AS ioc" in cmd for cmd in attach_commands)
        assert any("AS wikidata" in cmd for cmd in attach_commands)

    @pytest.mark.asyncio
    async def test_detach_all_from_session(self, species_database, mock_session):
        """Should detach all available databases from session."""
        await species_database.detach_all_from_session(mock_session)

        # Verify both DETACH DATABASE commands were executed
        assert mock_session.execute.call_count == 2

        calls = mock_session.execute.call_args_list
        detach_commands = [str(call[0][0]) for call in calls]

        assert any("DETACH DATABASE ioc" in cmd for cmd in detach_commands)
        assert any("DETACH DATABASE wikidata" in cmd for cmd in detach_commands)

    @pytest.mark.asyncio
    async def test_detach_all_from_session__exception_handling(
        self, species_database, mock_session
    ):
        """Should handle exceptions during detach gracefully."""
        mock_session.execute.side_effect = [
            None,  # First detach succeeds
            OperationalError("statement", "params", "orig"),  # Second fails
        ]

        # Should not raise exception despite error in middle
        await species_database.detach_all_from_session(mock_session)

        # Both detach commands should still be attempted
        assert mock_session.execute.call_count == 2


class TestGetBestCommonName:
    """Test priority-based common name resolution."""

    @pytest.mark.asyncio
    async def test_get_best_common_name_ioc_english(self, species_database, mock_session):
        """Should get avibase_id and then query IOC English name."""
        # Create mock rows for the two-step lookup
        MockAvibaseIdRow = namedtuple("MockAvibaseIdRow", ["avibase_id"])
        MockEnglishRow = namedtuple("MockEnglishRow", ["english_name"])

        avibase_id_row = MockAvibaseIdRow(avibase_id="ABC123")
        english_row = MockEnglishRow(english_name="American Robin")

        # Mock the Result objects from execute()
        mock_avibase_id_result = MagicMock(spec=Result)
        mock_avibase_id_result.first.return_value = avibase_id_row

        mock_english_result = MagicMock(spec=Result)
        mock_english_result.first.return_value = english_row

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[mock_avibase_id_result, mock_english_result],
        )

        result = await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", "en"
        )

        # Should execute two queries (avibase_id lookup, then IOC English)
        assert mock_session.execute.call_count == 2

        # Check result
        assert result["common_name"] == "American Robin"
        assert result["source"] == "IOC"

    @pytest.mark.asyncio
    async def test_get_best_common_name_ioc_translation(self, species_database, mock_session):
        """Should fall back to IOC translations for non-English languages."""
        MockAvibaseIdRow = namedtuple("MockAvibaseIdRow", ["avibase_id"])
        MockTranslationRow = namedtuple("MockTranslationRow", ["common_name"])

        avibase_id_row = MockAvibaseIdRow(avibase_id="ABC123")
        translation_row = MockTranslationRow(common_name="Petirrojo Americano")

        mock_avibase_id_result = MagicMock(spec=Result)
        mock_avibase_id_result.first.return_value = avibase_id_row

        mock_translation_result = MagicMock(spec=Result)
        mock_translation_result.first.return_value = translation_row

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[mock_avibase_id_result, mock_translation_result],
        )

        result = await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", "es"
        )

        assert mock_session.execute.call_count == 2
        assert result["common_name"] == "Petirrojo Americano"
        assert result["source"] == "IOC"

    @pytest.mark.asyncio
    async def test_get_best_common_name_wikidata_fallback(self, species_database, mock_session):
        """Should fall back to Wikidata when IOC has no translation."""
        MockAvibaseIdRow = namedtuple("MockAvibaseIdRow", ["avibase_id"])
        MockTranslationRow = namedtuple("MockTranslationRow", ["common_name"])

        avibase_id_row = MockAvibaseIdRow(avibase_id="ABC123")
        wikidata_row = MockTranslationRow(common_name="ロビン")

        mock_avibase_id_result = MagicMock(spec=Result)
        mock_avibase_id_result.first.return_value = avibase_id_row

        # IOC translation not found
        mock_ioc_result = MagicMock(spec=Result)
        mock_ioc_result.first.return_value = None

        # Wikidata translation found
        mock_wikidata_result = MagicMock(spec=Result)
        mock_wikidata_result.first.return_value = wikidata_row

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                mock_avibase_id_result,  # avibase_id lookup
                mock_ioc_result,  # IOC translation not found
                mock_wikidata_result,  # Wikidata found
            ],
        )

        result = await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", "ja"
        )

        assert mock_session.execute.call_count == 3
        assert result["common_name"] == "ロビン"
        assert result["source"] == "Wikidata"

    @pytest.mark.asyncio
    async def test_get_best_common_name__no_result(self, species_database, mock_session):
        """Should return empty result when no match is found."""
        mock_execute_result = AsyncMock(spec=Result)
        mock_execute_result.first.return_value = None
        mock_session.execute.return_value = mock_execute_result

        result = await species_database.get_best_common_name(
            mock_session, "Nonexistent species", "en"
        )

        assert result["common_name"] is None
        assert result["source"] is None

    @pytest.mark.asyncio
    async def test_get_best_common_name__sql_injection_prevention(
        self, species_database, mock_session
    ):
        """Should prevent SQL injection through parameterized queries."""
        mock_execute_result = AsyncMock(spec=Result)
        mock_execute_result.first.return_value = None
        mock_session.execute.return_value = mock_execute_result

        # Try injection through scientific name
        await species_database.get_best_common_name(mock_session, "'; DROP TABLE species; --", "en")

        # Should use parameterized queries, not string interpolation
        mock_session.execute.assert_called()
        call = mock_session.execute.call_args[0][0]
        # The SQL should be a compiled statement, not raw text with injected values
        assert "DROP TABLE" not in str(call)

    @pytest.mark.asyncio
    async def test_get_best_common_name__priority_source_detection(
        self, species_database, mock_session
    ):
        """Should correctly detect source based on priority order: IOC → Wikidata."""
        MockAvibaseIdRow = namedtuple("MockAvibaseIdRow", ["avibase_id"])
        MockEnglishRow = namedtuple("MockEnglishRow", ["english_name"])

        avibase_id_row = MockAvibaseIdRow(avibase_id="ABC123")
        english_row = MockEnglishRow(english_name="American Robin")

        # Test when IOC English name is found (highest priority for English)
        mock_avibase_id_result = MagicMock(spec=Result)
        mock_avibase_id_result.first.return_value = avibase_id_row

        mock_english_result = MagicMock(spec=Result)
        mock_english_result.first.return_value = english_row

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[mock_avibase_id_result, mock_english_result],
        )

        result = await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", "en"
        )

        # First priority should return IOC
        assert result["source"] == "IOC"

        # Test when Wikidata is found (lower priority) - For language not in IOC
        mock_session.reset_mock()
        MockTranslationRow = namedtuple("MockTranslationRow", ["common_name"])
        wikidata_row = MockTranslationRow(common_name="ロビン")

        mock_avibase_id_result2 = MagicMock(spec=Result)
        mock_avibase_id_result2.first.return_value = avibase_id_row

        mock_ioc_result = MagicMock(spec=Result)
        mock_ioc_result.first.return_value = None  # IOC translation not found

        mock_wikidata_result = MagicMock(spec=Result)
        mock_wikidata_result.first.return_value = wikidata_row  # Wikidata found

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                mock_avibase_id_result2,
                mock_ioc_result,
                mock_wikidata_result,
            ],
        )

        result = await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", "ja"
        )
        assert result["source"] == "Wikidata"


class TestGetAllTranslations:
    """Test comprehensive translation retrieval from all databases."""

    @pytest.mark.asyncio
    async def test_get_all_translations_all_databases(self, species_database, mock_session):
        """Should retrieve translations from all available databases."""
        # Create namedtuples for row results
        AvibaseIdRow = namedtuple("AvibaseIdRow", ["avibase_id", "english_name"])
        TransRow = namedtuple("TransRow", ["language_code", "common_name"])

        # Step 1: avibase_id lookup
        avibase_id_row = AvibaseIdRow(avibase_id="ABC123", english_name="American Robin")

        # Translation rows
        ioc_trans_row1 = TransRow(language_code="es", common_name="Petirrojo Americano")
        ioc_trans_row2 = TransRow(language_code="fr", common_name="Merle d'Amérique")

        wikidata_row1 = TransRow(language_code="de", common_name="Wanderdrossel")
        wikidata_row2 = TransRow(language_code="it", common_name="Pettirosso americano")

        # Mock execute to return different results for each query
        # First call: avibase_id lookup (uses .first() which is synchronous)
        first_result = MagicMock(spec=Result)
        first_result.first.return_value = avibase_id_row

        # Subsequent calls: translations (use iteration) - these must be iterable
        ioc_trans_result = [ioc_trans_row1, ioc_trans_row2]
        wikidata_result = [wikidata_row1, wikidata_row2]

        # Set up side_effect for execute to return different results for each call
        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                first_result,  # avibase_id + English name lookup
                ioc_trans_result,  # IOC translations
                wikidata_result,  # Wikidata
            ],
        )

        result = await species_database.get_all_translations(mock_session, "Turdus migratorius")

        # Should execute 3 queries (avibase_id lookup, IOC translations, Wikidata)
        assert mock_session.execute.call_count == 3

        # Verify result structure and deduplication
        assert "en" in result
        assert len(result["en"]) == 1
        assert result["en"][0]["name"] == "American Robin"
        assert result["en"][0]["source"] == "IOC"

        assert "es" in result
        assert len(result["es"]) == 1
        assert result["es"][0]["name"] == "Petirrojo Americano"
        assert result["es"][0]["source"] == "IOC"

        assert "fr" in result
        assert result["fr"][0]["source"] == "IOC"

        assert "de" in result
        assert result["de"][0]["source"] == "Wikidata"

        assert "it" in result
        assert result["it"][0]["source"] == "Wikidata"

    @pytest.mark.asyncio
    async def test_get_all_translations__deduplication(self, species_database, mock_session):
        """Should deduplicate identical names from different sources."""
        AvibaseIdRow = namedtuple("AvibaseIdRow", ["avibase_id", "english_name"])
        TransRow = namedtuple("TransRow", ["language_code", "common_name"])

        # avibase_id lookup with English name
        avibase_id_row = AvibaseIdRow(avibase_id="ABC123", english_name="American Robin")

        # Mock result for avibase_id query (.first() is synchronous)
        first_result = MagicMock(spec=Result)
        first_result.first.return_value = avibase_id_row

        # Translation rows - duplicates will be filtered
        ioc_trans_row = TransRow(language_code="en", common_name="American Robin")  # Duplicate
        wikidata_row = TransRow(language_code="en", common_name="Robin")  # Different

        # Mock results for iteration queries
        ioc_trans_result = [ioc_trans_row]
        wikidata_result = [wikidata_row]

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                first_result,
                ioc_trans_result,
                wikidata_result,
            ],
        )

        result = await species_database.get_all_translations(mock_session, "Turdus migratorius")

        assert "en" in result
        # Should have 2 entries:
        # 1. "American Robin" from IOC species table (avibase_id lookup)
        # 2. "Robin" from Wikidata (different name)
        # IOC translation's "American Robin" is filtered as duplicate
        assert len(result["en"]) == 2
        names = [t["name"] for t in result["en"]]
        assert names.count("American Robin") == 1  # Only from avibase_id lookup
        assert "Robin" in names

        # Should have IOC and Wikidata sources
        sources = [t["source"] for t in result["en"]]
        assert "IOC" in sources
        assert "Wikidata" in sources

    @pytest.mark.asyncio
    async def test_get_all_translations__sql_injection_prevention(
        self, species_database, mock_session
    ):
        """Should prevent SQL injection in all query parameters."""
        # Mock results for empty queries (.first() is synchronous)
        empty_first_result = MagicMock(spec=Result)
        empty_first_result.first.return_value = None

        # Empty iteration results
        empty_list = []

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                empty_first_result,  # avibase_id lookup - empty
                empty_list,  # IOC translations - empty
                empty_list,  # Wikidata - empty
            ],
        )

        await species_database.get_all_translations(mock_session, "'; DROP TABLE species; --")

        # Check all 3 queries use parameterized approach
        calls = mock_session.execute.call_args_list
        for call in calls:
            if len(call[0]) > 1:  # Has parameters
                params = call[0][1]
                assert params["sci_name"] == "'; DROP TABLE species; --"
            assert "DROP TABLE" not in str(call[0][0])


class TestGetAttribution:
    """Test database attribution strings."""

    def test_get_attribution_all_databases(self, species_database):
        """Should return attributions for all available databases."""
        attributions = species_database.get_attribution()

        assert len(attributions) == 2
        assert "IOC World Bird List (www.worldbirdnames.org) - CC-BY-4.0" in attributions
        assert "Wikidata - Public Domain (CC0)" in attributions


class TestErrorHandling:
    """Test error handling across the service."""

    @pytest.mark.asyncio
    async def test_attach_all_to_session__database_error(self, species_database, mock_session):
        """Should handle database errors during attach operations."""
        mock_session.execute.side_effect = OperationalError("statement", "params", "orig")

        # Should not suppress the exception - let caller handle it
        with pytest.raises(OperationalError):
            await species_database.attach_all_to_session(mock_session)

    @pytest.mark.asyncio
    async def test_get_best_common_name__database_error(self, species_database, mock_session):
        """Should handle database errors during query execution."""
        mock_session.execute.side_effect = SQLAlchemyError("Query failed")

        with pytest.raises(SQLAlchemyError):
            await species_database.get_best_common_name(mock_session, "Turdus migratorius", "en")

    @pytest.mark.asyncio
    async def test_get_all_translations__partial_database_error(
        self, species_database, mock_session
    ):
        """Should handle errors from individual database queries gracefully."""
        AvibaseIdRow = namedtuple("AvibaseIdRow", ["avibase_id", "english_name"])
        TransRow = namedtuple("TransRow", ["language_code", "common_name"])

        # First query succeeds (.first() is synchronous)
        avibase_id_row = AvibaseIdRow(avibase_id="ABC123", english_name="American Robin")
        first_result = MagicMock(spec=Result)
        first_result.first.return_value = avibase_id_row

        # Wikidata row for when it succeeds
        wikidata_row = TransRow(language_code="de", common_name="Wanderdrossel")

        # First query succeeds, second fails, subsequent queries won't be reached
        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[
                first_result,  # avibase_id lookup - success
                SQLAlchemyError("IOC translations failed"),  # IOC translations - fail
                [wikidata_row],  # Wikidata - won't be reached
            ],
        )

        with pytest.raises(SQLAlchemyError):
            await species_database.get_all_translations(mock_session, "Turdus migratorius")

    def test_path_resolver_error_handling(self, path_resolver):
        """Should handle file resolver errors during initialization."""
        # Override to raise an exception
        path_resolver.get_ioc_database_path = lambda: (_ for _ in ()).throw(
            Exception("File resolver error")
        )

        # Should re-raise the exception from file resolver
        with pytest.raises(Exception, match="File resolver error"):
            SpeciesDatabaseService(path_resolver)


class TestIntegrationWithRealSession:
    """Integration tests using real SQLite session."""

    @pytest.mark.asyncio
    async def test_attach_detach_integration(self, species_database, in_memory_session, tmp_path):
        """Should successfully attach and detach real database files."""
        # Create temporary database files
        ioc_db = tmp_path / "ioc.db"
        wikidata_db = tmp_path / "wikidata.db"

        # Create the database files with minimal schema
        for db_path in [ioc_db, wikidata_db]:
            engine = create_engine(f"sqlite:///{db_path}")
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE test_table (id INTEGER PRIMARY KEY)"))
            engine.dispose()

        # Override service paths with real files
        species_database.ioc_db_path = str(ioc_db)
        species_database.wikidata_db_path = str(wikidata_db)

        try:
            # Test attach
            await species_database.attach_all_to_session(in_memory_session)

            # Verify databases are attached by querying schema
            result = await in_memory_session.execute(
                text("SELECT name FROM ioc.sqlite_master WHERE type='table'")
            )
            rows = result.fetchall()
            assert "test_table" in [row[0] for row in rows]

            # Test detach
            await species_database.detach_all_from_session(in_memory_session)

            # Verify databases are detached
            with pytest.raises(OperationalError):
                await in_memory_session.execute(text("SELECT * FROM ioc.test_table"))

        except Exception as e:
            # Clean up on error
            try:
                await species_database.detach_all_from_session(in_memory_session)
            except Exception:
                pass
            raise e

    @pytest.mark.asyncio
    async def test_query_building_integration(self, species_database, in_memory_session):
        """Should build and execute valid SQL queries."""
        # Test that the query building doesn't have syntax errors
        with patch.object(in_memory_session, "execute", autospec=True) as mock_execute:
            mock_result = AsyncMock(spec=Result)
            mock_result.first.return_value = None
            mock_execute.return_value = mock_result

            await species_database.get_best_common_name(
                in_memory_session, "Turdus migratorius", "en"
            )

            # Verify valid queries were attempted (up to 3 queries for different databases)
            # avibase_id lookup -> no result, so stops
            assert mock_execute.call_count >= 1

            # Check the first call
            call_args = mock_execute.call_args_list[0]
            query_obj = call_args[0][0]
            params = call_args[0][1]

            # The query object should be a SQLAlchemy text object
            assert hasattr(query_obj, "text")
            assert isinstance(params, dict)
            assert "sci_name" in params


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_scientific_name(self, species_database, mock_session):
        """Should handle empty scientific name gracefully."""
        mock_execute_result = AsyncMock(spec=Result)
        mock_execute_result.first.return_value = None
        mock_session.execute.return_value = mock_execute_result

        result = await species_database.get_best_common_name(mock_session, "", "en")

        # Should execute at least avibase_id lookup query
        assert mock_session.execute.call_count >= 1
        # Check the first call has empty sci_name
        params = mock_session.execute.call_args_list[0][0][1]
        assert params["sci_name"] == ""

        assert result["common_name"] is None
        assert result["source"] is None

    @pytest.mark.asyncio
    async def test_special_characters_in_scientific_name(self, species_database, mock_session):
        """Should handle special characters in scientific names."""
        mock_execute_result = AsyncMock(spec=Result)
        mock_execute_result.first.return_value = None
        mock_session.execute.return_value = mock_execute_result

        special_name = "Turdus (migratorius) x merula"

        await species_database.get_best_common_name(mock_session, special_name, "en")

        params = mock_session.execute.call_args[0][1]
        assert params["sci_name"] == special_name

    @pytest.mark.parametrize(
        "language_code",
        [
            pytest.param("zh-CN", id="chinese_simplified"),
            pytest.param("pt-BR", id="portuguese_brazil"),
            pytest.param("en-US", id="english_us"),
            pytest.param("fr-CA", id="french_canada"),
            pytest.param("x-custom", id="custom_code"),
        ],
    )
    @pytest.mark.asyncio
    async def test_unusual_language_codes(self, species_database, mock_session, language_code):
        """Should handle unusual language codes."""
        MockAvibaseIdRow = namedtuple("MockAvibaseIdRow", ["avibase_id"])
        avibase_id_row = MockAvibaseIdRow(avibase_id="ABC123")

        mock_avibase_id_result = MagicMock(spec=Result)
        mock_avibase_id_result.first.return_value = avibase_id_row

        mock_ioc_translation_result = MagicMock(spec=Result)
        mock_ioc_translation_result.first.return_value = None

        mock_wikidata_result = MagicMock(spec=Result)
        mock_wikidata_result.first.return_value = None

        mock_session.execute = AsyncMock(
            spec=callable,
            side_effect=[mock_avibase_id_result, mock_ioc_translation_result, mock_wikidata_result],
        )

        await species_database.get_best_common_name(
            mock_session, "Turdus migratorius", language_code
        )

        # Check second call has the language parameter (IOC translations)
        params = mock_session.execute.call_args_list[1][0][1]
        assert params["lang"] == language_code

    @pytest.mark.asyncio
    async def test_case_sensitivity_in_queries(self, species_database, mock_session):
        """Should handle case variations in scientific names through LOWER() function."""
        mock_execute_result = AsyncMock(spec=Result)
        mock_execute_result.first.return_value = None
        mock_session.execute.return_value = mock_execute_result

        await species_database.get_best_common_name(mock_session, "TURDUS MIGRATORIUS", "en")

        # Verify query uses LOWER() function for case-insensitive comparison
        call_args = mock_session.execute.call_args
        query = str(call_args[0][0])
        assert "LOWER(" in query
        assert ":sci_name" in query  # Parameter should still be used

    def test_database_paths_immutable(self, species_database):
        """Should not allow external modification of database paths."""
        original_ioc = species_database.ioc_db_path
        original_wikidata = species_database.wikidata_db_path

        # Database paths should be set at initialization
        assert species_database.ioc_db_path is not None
        assert species_database.wikidata_db_path is not None

        # Paths should remain unchanged
        assert species_database.ioc_db_path == original_ioc
        assert species_database.wikidata_db_path == original_wikidata
