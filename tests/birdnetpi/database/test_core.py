from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.core import CoreDatabaseService


@pytest_asyncio.fixture
async def core_database_service(tmp_path):
    """Provide a CoreDatabaseService instance for testing."""
    db_path = tmp_path / "test.db"

    # Patch problematic parts during initialization
    with patch("birdnetpi.database.core.SQLModel.metadata.create_all"):
        service = CoreDatabaseService(db_path)

    # The service is now created without trying to initialize the database
    # The methods we're testing will be properly mocked in each test
    try:
        yield service
    finally:
        # Dispose resources to prevent file descriptor leaks
        if (
            hasattr(service, "async_engine")
            and service.async_engine
            and not isinstance(service.async_engine, MagicMock)
        ):
            await service.async_engine.dispose()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_clear_database(core_database_service):
    """Should clear all data from the database tables successfully"""
    # Mock the database session to avoid actual database operations
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        # Mock SQLModel.metadata.sorted_tables as a property
        mock_table = MagicMock()
        mock_table.delete.return_value = MagicMock()

        with patch(
            "birdnetpi.database.core.SQLModel.metadata", new_callable=PropertyMock
        ) as mock_metadata:
            mock_metadata.return_value.sorted_tables = [mock_table]
            await core_database_service.clear_database()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_clear_database_failure(core_database_service):
    """Should handle clear database failure and rollback"""
    # Mock the database session to simulate a failure
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("Test Error")
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        # Mock SQLModel.metadata.sorted_tables
        mock_table = MagicMock()
        mock_table.delete.return_value = MagicMock()

        with patch(
            "birdnetpi.database.core.SQLModel.metadata", new_callable=PropertyMock
        ) as mock_metadata:
            mock_metadata.return_value.sorted_tables = [mock_table]

            with pytest.raises(SQLAlchemyError):
                await core_database_service.clear_database()

            mock_session.rollback.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_checkpoint_wal(core_database_service):
    """Should successfully checkpoint WAL file"""
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()

        # Create a mock result object with fetchone method
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0, 10, 10)  # busy, log_pages, checkpointed
        mock_session.execute.return_value = mock_result

        # Setup async context manager
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        await core_database_service.checkpoint_wal("RESTART")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_checkpoint_wal_failure(core_database_service):
    """Should handle WAL checkpoint failure gracefully"""
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("WAL Error")
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        # Should not raise exception, just print warning
        await core_database_service.checkpoint_wal("RESTART")

        mock_session.execute.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_get_database_stats(core_database_service, tmp_path):
    """Should return database statistics"""
    # Create fake database files
    db_path = tmp_path / "test.db"
    db_path.write_text("fake db content")

    wal_path = tmp_path / "test.db-wal"
    wal_path.write_text("fake wal")

    shm_path = tmp_path / "test.db-shm"
    shm_path.write_text("fake shm")

    # Mock the database path and session queries
    core_database_service.db_path = db_path

    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()

        # Mock pragma results
        mock_results = [
            MagicMock(fetchone=lambda: [1000]),  # page_count
            MagicMock(fetchone=lambda: [4096]),  # page_size
            MagicMock(fetchone=lambda: [0, 50, 50]),  # wal_checkpoint
            MagicMock(fetchone=lambda: ["wal"]),  # journal_mode
        ]
        mock_session.execute.side_effect = mock_results
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        stats = await core_database_service.get_database_stats()

        # Verify file size calculations
        assert "main_db_size" in stats
        assert "wal_size" in stats
        assert "shm_size" in stats
        assert "total_size" in stats
        assert stats["total_size"] == stats["main_db_size"] + stats["wal_size"] + stats["shm_size"]

        # Verify SQLite stats
        assert stats["page_count"] == 1000
        assert stats["page_size"] == 4096
        assert stats["journal_mode"] == "wal"


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_vacuum_database(core_database_service):
    """Should successfully vacuum database"""
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        await core_database_service.vacuum_database()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_vacuum_database_failure(core_database_service):
    """Should handle vacuum database failure"""
    with patch.object(core_database_service, "get_async_db") as mock_get_async_db:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = SQLAlchemyError("Vacuum Error")
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        with pytest.raises(SQLAlchemyError):
            await core_database_service.vacuum_database()

        mock_session.rollback.assert_called_once()
