from unittest.mock import MagicMock, PropertyMock, create_autospec, patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.core import CoreDatabaseService


@pytest_asyncio.fixture
async def core_database_service(tmp_path):
    """Provide a CoreDatabaseService instance for testing."""
    db_path = tmp_path / "test.db"

    # Patch problematic parts during initialization
    with patch("birdnetpi.database.core.SQLModel.metadata.create_all", autospec=True):
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
@pytest.mark.parametrize(
    "operation,should_fail,exception",
    [
        pytest.param("clear", False, None, id="clear_database_success"),
        pytest.param("clear", True, SQLAlchemyError("Test Error"), id="clear_database_failure"),
        pytest.param("vacuum", False, None, id="vacuum_database_success"),
        pytest.param("vacuum", True, SQLAlchemyError("Vacuum Error"), id="vacuum_database_failure"),
    ],
)
async def test_database_operations(
    core_database_service, operation, should_fail, exception, db_session_factory
):
    """Should handle database clear/vacuum operations correctly."""
    with patch.object(core_database_service, "get_async_db", autospec=True) as mock_get_async_db:
        mock_session, _result = db_session_factory()
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        if operation == "clear":
            # Mock SQLModel.metadata.sorted_tables for clear operation
            from sqlalchemy import Table

            mock_table = create_autospec(Table, spec_set=True, name="test_table")
            mock_table.delete.return_value = create_autospec(spec=["__str__"], spec_set=True)

            with patch(
                "birdnetpi.database.core.SQLModel.metadata", new_callable=PropertyMock
            ) as mock_metadata:
                mock_metadata.return_value.sorted_tables = [mock_table]

                if should_fail:
                    mock_session.execute.side_effect = exception
                    with pytest.raises(SQLAlchemyError):
                        await core_database_service.clear_database()
                    mock_session.rollback.assert_called_once()
                else:
                    await core_database_service.clear_database()
                    mock_session.execute.assert_called_once()
                    mock_session.commit.assert_called_once()

        else:  # vacuum operation
            if should_fail:
                mock_session.execute.side_effect = exception
                with pytest.raises(SQLAlchemyError):
                    await core_database_service.vacuum_database()
                mock_session.rollback.assert_called_once()
            else:
                await core_database_service.vacuum_database()
                mock_session.execute.assert_called_once()
                mock_session.commit.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checkpoint_type,should_fail",
    [
        pytest.param("RESTART", False, id="checkpoint_wal_restart_success"),
        pytest.param("RESTART", True, id="checkpoint_wal_restart_failure"),
    ],
)
async def test_checkpoint_wal(
    core_database_service, checkpoint_type, should_fail, db_session_factory
):
    """Should handle WAL checkpoint operations correctly."""
    with patch.object(core_database_service, "get_async_db", autospec=True) as mock_get_async_db:
        mock_session, _result = db_session_factory()
        mock_get_async_db.return_value.__aenter__.return_value = mock_session

        if should_fail:
            # Configure the side effect on the already-spec'd async method
            mock_session.execute.side_effect = SQLAlchemyError("WAL Error")
            # Should not raise exception, just print warning
            await core_database_service.checkpoint_wal(checkpoint_type)
            mock_session.execute.assert_called_once()
        else:
            # Create a mock result object with fetchone method
            from sqlalchemy.engine import Result

            mock_result = create_autospec(Result, spec_set=True)
            mock_result.fetchone.return_value = (0, 10, 10)  # busy, log_pages, checkpointed
            # Configure the return value on the already-spec'd async method
            mock_session.execute.return_value = mock_result

            await core_database_service.checkpoint_wal(checkpoint_type)
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_get_database_stats(core_database_service, tmp_path, db_session_factory):
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

    with patch.object(core_database_service, "get_async_db", autospec=True) as mock_get_async_db:
        mock_session, _result = db_session_factory()

        # Mock pragma results
        from sqlalchemy.engine import Result

        mock_result_1 = create_autospec(Result, spec_set=True, instance=True)
        mock_result_1.fetchone.return_value = [1000]  # page_count

        mock_result_2 = create_autospec(Result, spec_set=True, instance=True)
        mock_result_2.fetchone.return_value = [4096]  # page_size

        mock_result_3 = create_autospec(Result, spec_set=True, instance=True)
        mock_result_3.fetchone.return_value = [0, 50, 50]  # wal_checkpoint

        mock_result_4 = create_autospec(Result, spec_set=True, instance=True)
        mock_result_4.fetchone.return_value = ["wal"]  # journal_mode

        mock_results = [mock_result_1, mock_result_2, mock_result_3, mock_result_4]
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
