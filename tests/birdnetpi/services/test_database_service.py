from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.database_service import DatabaseService


@pytest.fixture
def bnp_database_service(tmp_path) -> DatabaseService:
    """Provide a DatabaseService instance for testing."""
    db_path = tmp_path / "test.db"
    return DatabaseService(db_path)


def test_clear_database(bnp_database_service):
    """Should clear all data from the database tables successfully"""
    # This test now checks that the clear_database method runs without error.
    # A more thorough test would involve adding data and then checking that it was deleted.
    bnp_database_service.clear_database()


def test_clear_database_failure(bnp_database_service, monkeypatch):
    """Should handle clear database failure and rollback"""
    # We now need to mock the session object used by the service
    mock_session = MagicMock()
    mock_session.execute.side_effect = SQLAlchemyError("Test Error")
    monkeypatch.setattr(bnp_database_service, "session_local", lambda: mock_session)

    with pytest.raises(SQLAlchemyError):
        bnp_database_service.clear_database()

    mock_session.rollback.assert_called_once()


def test_checkpoint_wal(bnp_database_service):
    """Should successfully checkpoint WAL file"""
    with patch.object(bnp_database_service, "get_db") as mock_get_db:
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = (
            0,
            100,
            100,
        )  # busy, log_pages, checkpointed
        mock_get_db.return_value.__enter__.return_value = mock_session

        bnp_database_service.checkpoint_wal("RESTART")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


def test_checkpoint_wal_failure(bnp_database_service):
    """Should handle WAL checkpoint failure gracefully"""
    with patch.object(bnp_database_service, "get_db") as mock_get_db:
        mock_session = MagicMock()
        mock_session.execute.side_effect = SQLAlchemyError("WAL Error")
        mock_get_db.return_value.__enter__.return_value = mock_session

        # Should not raise exception, just print warning
        bnp_database_service.checkpoint_wal("RESTART")

        mock_session.execute.assert_called_once()


def test_get_database_stats(bnp_database_service, tmp_path):
    """Should return database statistics"""
    # Create fake database files
    db_path = tmp_path / "test.db"
    db_path.write_text("fake db content")

    wal_path = tmp_path / "test.db-wal"
    wal_path.write_text("fake wal")

    shm_path = tmp_path / "test.db-shm"
    shm_path.write_text("fake shm")

    # Mock the database path and session queries
    bnp_database_service.db_path = db_path

    with patch.object(bnp_database_service, "get_db") as mock_get_db:
        mock_session = MagicMock()

        # Mock pragma results
        mock_session.execute.side_effect = [
            MagicMock(fetchone=lambda: [1000]),  # page_count
            MagicMock(fetchone=lambda: [4096]),  # page_size
            MagicMock(fetchone=lambda: [0, 50, 50]),  # wal_checkpoint
            MagicMock(fetchone=lambda: ["wal"]),  # journal_mode
        ]
        mock_get_db.return_value.__enter__.return_value = mock_session

        stats = bnp_database_service.get_database_stats()

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


def test_vacuum_database(bnp_database_service):
    """Should successfully vacuum database"""
    with patch.object(bnp_database_service, "get_db") as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_session

        bnp_database_service.vacuum_database()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


def test_vacuum_database_failure(bnp_database_service):
    """Should handle vacuum database failure"""
    with patch.object(bnp_database_service, "get_db") as mock_get_db:
        mock_session = MagicMock()
        mock_session.execute.side_effect = SQLAlchemyError("Vacuum Error")
        mock_get_db.return_value.__enter__.return_value = mock_session

        with pytest.raises(SQLAlchemyError):
            bnp_database_service.vacuum_database()

        mock_session.rollback.assert_called_once()
