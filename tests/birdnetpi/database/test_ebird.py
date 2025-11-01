"""Tests for eBird regional confidence service."""

from collections import namedtuple
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Result
from sqlalchemy.exc import OperationalError

from birdnetpi.database.ebird import EBirdRegionService


@pytest.fixture
def mock_path_resolver(path_resolver, tmp_path):
    """Create mock path resolver with test eBird pack paths.

    Uses the global path_resolver fixture as a base to prevent MagicMock file creation.
    """
    # Create test database file in temp directory
    test_ebird_db = tmp_path / "database" / "test-pack-2025.08.db"
    test_ebird_db.parent.mkdir(parents=True, exist_ok=True)
    test_ebird_db.touch()

    # Override the ebird pack path method
    path_resolver.get_ebird_pack_path = lambda name: test_ebird_db

    return path_resolver


@pytest.fixture
def ebird_service(mock_path_resolver):
    """Create eBird region service with mocked paths."""
    return EBirdRegionService(mock_path_resolver)


@pytest.fixture
def mock_session(db_session_factory):
    """Create mock SQLAlchemy async session using factory."""
    session, _result = db_session_factory()
    return session


@pytest.fixture
async def in_memory_session(async_in_memory_session):
    """Use the global async session fixture for integration tests."""
    return async_in_memory_session


class TestEBirdRegionServiceInitialization:
    """Test eBird region service initialization."""

    def test_service_initialization(self, path_resolver):
        """Should initialize service with path resolver."""
        service = EBirdRegionService(path_resolver)

        assert service.path_resolver == path_resolver


class TestAttachDetachDatabases:
    """Test database attachment and detachment functionality."""

    @pytest.mark.asyncio
    async def test_attach_to_session_success(self, ebird_service, mock_session):
        """Should attach eBird pack database to session."""
        await ebird_service.attach_to_session(mock_session, "test-pack-2025.08")

        # Verify ATTACH DATABASE command was executed
        assert mock_session.execute.call_count == 1

        call_args = mock_session.execute.call_args
        attach_command = str(call_args[0][0])

        assert "ATTACH DATABASE" in attach_command
        assert "AS ebird" in attach_command

    @pytest.mark.asyncio
    async def test_attach_to_session_missing_pack(self, ebird_service, mock_session, tmp_path):
        """Should raise FileNotFoundError when pack doesn't exist."""
        # Override to point to non-existent file
        ebird_service.path_resolver.get_ebird_pack_path = lambda name: tmp_path / "missing.db"

        with pytest.raises(FileNotFoundError, match="eBird pack not found"):
            await ebird_service.attach_to_session(mock_session, "missing-pack")

    @pytest.mark.asyncio
    async def test_detach_from_session(self, ebird_service, mock_session):
        """Should detach eBird pack database from session."""
        await ebird_service.detach_from_session(mock_session)

        # Verify DETACH DATABASE command was executed
        assert mock_session.execute.call_count == 1

        call_args = mock_session.execute.call_args
        detach_command = str(call_args[0][0])

        assert "DETACH DATABASE ebird" in detach_command

    @pytest.mark.asyncio
    async def test_detach_from_session_exception_handling(self, ebird_service, mock_session):
        """Should handle exceptions during detach gracefully."""
        mock_session.execute.side_effect = OperationalError("statement", "params", "orig")

        # Should not raise exception despite error
        await ebird_service.detach_from_session(mock_session)

        # Detach command should still be attempted
        assert mock_session.execute.call_count == 1


class TestGetSpeciesConfidenceTier:
    """Test confidence tier lookup for species at specific locations."""

    @pytest.mark.asyncio
    async def test_get_species_confidence_tier_found(self, ebird_service, mock_session):
        """Should return confidence tier for species in cell."""
        MockRow = namedtuple("MockRow", ["confidence_tier"])
        tier_row = MockRow(confidence_tier="common")

        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = tier_row
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_species_confidence_tier(
            mock_session, "Cyanocitta cristata", "85283473fffffff"
        )

        assert result == "common"
        assert mock_session.execute.call_count == 1

        # Verify parameterized query
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        params = call_args[1]

        assert ":h3_cell" in query
        assert ":scientific_name" in query
        assert params["scientific_name"] == "Cyanocitta cristata"
        assert params["h3_cell"] == int("85283473fffffff", 16)

    @pytest.mark.asyncio
    async def test_get_species_confidence_tier_not_found(self, ebird_service, mock_session):
        """Should return None when species not in cell."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_species_confidence_tier(
            mock_session, "Nonexistent species", "85283473fffffff"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_species_confidence_tier_invalid_h3(self, ebird_service, mock_session):
        """Should handle invalid H3 cell format."""
        result = await ebird_service.get_species_confidence_tier(
            mock_session, "Cyanocitta cristata", "not-a-hex-value"
        )

        assert result is None
        # Should not execute query with invalid cell
        assert mock_session.execute.call_count == 0

    @pytest.mark.parametrize(
        "tier",
        [
            pytest.param("vagrant", id="vagrant"),
            pytest.param("rare", id="rare"),
            pytest.param("uncommon", id="uncommon"),
            pytest.param("common", id="common"),
        ],
    )
    @pytest.mark.asyncio
    async def test_get_species_confidence_tier_all_tiers(self, ebird_service, mock_session, tier):
        """Should correctly return all tier types."""
        MockRow = namedtuple("MockRow", ["confidence_tier"])
        tier_row = MockRow(confidence_tier=tier)

        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = tier_row
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_species_confidence_tier(
            mock_session, "Test species", "85283473fffffff"
        )

        assert result == tier


class TestGetConfidenceBoost:
    """Test confidence boost multiplier lookup."""

    @pytest.mark.asyncio
    async def test_get_confidence_boost_found(self, ebird_service, mock_session):
        """Should return confidence boost multiplier for species in cell."""
        MockRow = namedtuple("MockRow", ["confidence_boost"])
        boost_row = MockRow(confidence_boost=1.5)

        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = boost_row
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_confidence_boost(
            mock_session, "Cyanocitta cristata", "85283473fffffff"
        )

        assert result == 1.5
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_get_confidence_boost_not_found(self, ebird_service, mock_session):
        """Should return None when no boost data available."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_confidence_boost(
            mock_session, "Nonexistent species", "85283473fffffff"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_confidence_boost_invalid_h3(self, ebird_service, mock_session):
        """Should handle invalid H3 cell format."""
        result = await ebird_service.get_confidence_boost(
            mock_session, "Cyanocitta cristata", "invalid-hex"
        )

        assert result is None


class TestIsSpeciesInRegion:
    """Test species presence check."""

    @pytest.mark.asyncio
    async def test_is_species_in_region_true(self, ebird_service, mock_session):
        """Should return True when species is in region."""
        MockRow = namedtuple("MockRow", ["confidence_tier"])
        tier_row = MockRow(confidence_tier="common")

        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = tier_row
        mock_session.execute.return_value = mock_result

        result = await ebird_service.is_species_in_region(
            mock_session, "Cyanocitta cristata", "85283473fffffff"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_is_species_in_region_false(self, ebird_service, mock_session):
        """Should return False when species not in region."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await ebird_service.is_species_in_region(
            mock_session, "Nonexistent species", "85283473fffffff"
        )

        assert result is False


class TestGetAllowedSpeciesForLocation:
    """Test allowed species retrieval based on strictness."""

    @pytest.mark.asyncio
    async def test_get_allowed_species_vagrant_strictness(self, ebird_service, mock_session):
        """Should filter out vagrant species."""
        MockRow = namedtuple("MockRow", ["scientific_name"])
        species_rows = [
            MockRow(scientific_name="Species 1"),
            MockRow(scientific_name="Species 2"),
        ]

        mock_session.execute.return_value = species_rows

        result = await ebird_service.get_allowed_species_for_location(
            mock_session, "85283473fffffff", "vagrant"
        )

        assert isinstance(result, set)
        assert "Species 1" in result
        assert "Species 2" in result

        # Verify query contains tier filter
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        assert "confidence_tier != 'vagrant'" in query

    @pytest.mark.asyncio
    async def test_get_allowed_species_rare_strictness(self, ebird_service, mock_session):
        """Should filter out vagrant and rare species."""
        MockRow = namedtuple("MockRow", ["scientific_name"])
        species_rows = [MockRow(scientific_name="Common species")]

        mock_session.execute.return_value = species_rows

        _result = await ebird_service.get_allowed_species_for_location(
            mock_session, "85283473fffffff", "rare"
        )

        # Verify query contains tier filter
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        assert "confidence_tier IN ('uncommon', 'common')" in query

    @pytest.mark.asyncio
    async def test_get_allowed_species_uncommon_strictness(self, ebird_service, mock_session):
        """Should allow only common species."""
        MockRow = namedtuple("MockRow", ["scientific_name"])
        species_rows = [MockRow(scientific_name="Common species")]

        mock_session.execute.return_value = species_rows

        _result = await ebird_service.get_allowed_species_for_location(
            mock_session, "85283473fffffff", "uncommon"
        )

        # Verify query contains tier filter
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        assert "confidence_tier = 'common'" in query

    @pytest.mark.asyncio
    async def test_get_allowed_species_common_strictness(self, ebird_service, mock_session):
        """Should allow only common species."""
        MockRow = namedtuple("MockRow", ["scientific_name"])
        species_rows = [MockRow(scientific_name="Common species")]

        mock_session.execute.return_value = species_rows

        _result = await ebird_service.get_allowed_species_for_location(
            mock_session, "85283473fffffff", "common"
        )

        # Verify query contains tier filter
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        assert "confidence_tier = 'common'" in query

    @pytest.mark.asyncio
    async def test_get_allowed_species_invalid_h3(self, ebird_service, mock_session):
        """Should return empty set for invalid H3 cell."""
        result = await ebird_service.get_allowed_species_for_location(
            mock_session, "invalid-hex", "vagrant"
        )

        assert result == set()
        assert mock_session.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_get_allowed_species_unknown_strictness(self, ebird_service, mock_session):
        """Should allow all species for unknown strictness level."""
        MockRow = namedtuple("MockRow", ["scientific_name"])
        species_rows = [MockRow(scientific_name="All species")]

        mock_session.execute.return_value = species_rows

        _result = await ebird_service.get_allowed_species_for_location(
            mock_session, "85283473fffffff", "unknown_level"
        )

        # Verify query allows all species
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        assert "1=1" in query


class TestSQLInjectionPrevention:
    """Test SQL injection prevention across all methods."""

    @pytest.mark.asyncio
    async def test_attach_path_injection_prevented(self, ebird_service, mock_session, tmp_path):
        """Should prevent SQL injection through database path."""
        # Create a valid database file
        test_db = tmp_path / "test.db"
        test_db.touch()

        # Override to return the path (no injection possible here since it's from PathResolver)
        ebird_service.path_resolver.get_ebird_pack_path = lambda name: test_db

        await ebird_service.attach_to_session(mock_session, "test'; DROP TABLE detections; --")

        # The pack name goes through PathResolver, which controls the path
        # Even malicious input cannot affect the path
        call_args = mock_session.execute.call_args[0]
        assert "DROP TABLE" not in str(call_args[0])

    @pytest.mark.asyncio
    async def test_species_name_injection_prevented(self, ebird_service, mock_session):
        """Should prevent SQL injection through scientific name parameter."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        await ebird_service.get_species_confidence_tier(
            mock_session, "'; DROP TABLE grid_species; --", "85283473fffffff"
        )

        # Verify parameterized query (not string interpolation)
        call_args = mock_session.execute.call_args[0]
        query = str(call_args[0])
        params = call_args[1]

        assert ":scientific_name" in query
        assert params["scientific_name"] == "'; DROP TABLE grid_species; --"
        assert "DROP TABLE" not in query


class TestIntegrationWithRealSession:
    """Integration tests using real SQLite session."""

    @pytest.mark.asyncio
    async def test_attach_detach_integration(self, ebird_service, in_memory_session, tmp_path):
        """Should successfully attach and detach real eBird pack database."""
        # Create temporary eBird pack database
        ebird_db = tmp_path / "test-pack.db"

        # Create the database with test schema
        engine = create_engine(f"sqlite:///{ebird_db}")
        with engine.begin() as conn:
            # Create species_lookup table
            conn.execute(
                text("""
                CREATE TABLE species_lookup (
                    avibase_id TEXT PRIMARY KEY,
                    scientific_name TEXT
                )
            """)
            )
            # Create grid_species table
            conn.execute(
                text("""
                CREATE TABLE grid_species (
                    h3_cell INTEGER,
                    avibase_id TEXT,
                    confidence_tier TEXT
                )
            """)
            )
            # Insert test data
            conn.execute(
                text("INSERT INTO species_lookup VALUES (:avibase_id, :scientific_name)"),
                {"avibase_id": "TEST001", "scientific_name": "Test species"},
            )
            conn.execute(
                text("INSERT INTO grid_species VALUES (:h3_cell, :avibase_id, :tier)"),
                {"h3_cell": 599686042433355775, "avibase_id": "TEST001", "tier": "common"},
            )
        engine.dispose()

        # Override service path with real file
        ebird_service.path_resolver.get_ebird_pack_path = lambda name: ebird_db

        try:
            # Test attach
            await ebird_service.attach_to_session(in_memory_session, "test-pack")

            # Verify database is attached by querying it
            result = await in_memory_session.execute(
                text("SELECT scientific_name FROM ebird.species_lookup")
            )
            rows = result.fetchall()
            assert "Test species" in [row[0] for row in rows]

            # Test detach
            await ebird_service.detach_from_session(in_memory_session)

            # Verify database is detached
            with pytest.raises(OperationalError):
                await in_memory_session.execute(text("SELECT * FROM ebird.grid_species"))

        except Exception as e:
            # Clean up on error
            try:
                await ebird_service.detach_from_session(in_memory_session)
            except Exception:
                pass
            raise e

    @pytest.mark.asyncio
    async def test_confidence_tier_query_integration(
        self, ebird_service, in_memory_session, tmp_path
    ):
        """Should successfully query confidence tier from real database."""
        # Create eBird pack database with test data
        ebird_db = tmp_path / "test-pack.db"

        engine = create_engine(f"sqlite:///{ebird_db}")
        with engine.begin() as conn:
            # Create species_lookup table
            conn.execute(
                text("""
                CREATE TABLE species_lookup (
                    avibase_id TEXT PRIMARY KEY,
                    scientific_name TEXT
                )
            """)
            )
            # Create grid_species table
            conn.execute(
                text("""
                CREATE TABLE grid_species (
                    h3_cell INTEGER,
                    avibase_id TEXT,
                    confidence_tier TEXT,
                    confidence_boost REAL
                )
            """)
            )
            # Insert test species
            conn.execute(
                text("INSERT INTO species_lookup VALUES (:avibase_id, :scientific_name)"),
                {"avibase_id": "TEST001", "scientific_name": "Cyanocitta cristata"},
            )
            # Use the hex value converted to int
            h3_int = int("85283473fffffff", 16)
            conn.execute(
                text("INSERT INTO grid_species VALUES (:h3_cell, :avibase_id, :tier, :boost)"),
                {"h3_cell": h3_int, "avibase_id": "TEST001", "tier": "common", "boost": 1.5},
            )
        engine.dispose()

        ebird_service.path_resolver.get_ebird_pack_path = lambda name: ebird_db

        try:
            await ebird_service.attach_to_session(in_memory_session, "test-pack")

            # Query confidence tier
            tier = await ebird_service.get_species_confidence_tier(
                in_memory_session, "Cyanocitta cristata", "85283473fffffff"
            )

            assert tier == "common"

        finally:
            await ebird_service.detach_from_session(in_memory_session)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_scientific_name(self, ebird_service, mock_session):
        """Should handle empty scientific name."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await ebird_service.get_species_confidence_tier(
            mock_session, "", "85283473fffffff"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_special_characters_in_scientific_name(self, ebird_service, mock_session):
        """Should handle special characters in scientific names."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        special_name = "Species (subspecies) x hybrid"

        await ebird_service.get_species_confidence_tier(
            mock_session, special_name, "85283473fffffff"
        )

        params = mock_session.execute.call_args[0][1]
        assert params["scientific_name"] == special_name

    @pytest.mark.asyncio
    async def test_zero_h3_cell(self, ebird_service, mock_session):
        """Should handle H3 cell value of zero."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        await ebird_service.get_species_confidence_tier(
            mock_session, "Test species", "0000000000000000"
        )

        params = mock_session.execute.call_args[0][1]
        assert params["h3_cell"] == 0

    @pytest.mark.asyncio
    async def test_max_h3_cell(self, ebird_service, mock_session):
        """Should handle maximum H3 cell value."""
        mock_result = MagicMock(spec=Result)
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        await ebird_service.get_species_confidence_tier(
            mock_session, "Test species", "ffffffffffff"
        )

        params = mock_session.execute.call_args[0][1]
        assert params["h3_cell"] == int("ffffffffffff", 16)
