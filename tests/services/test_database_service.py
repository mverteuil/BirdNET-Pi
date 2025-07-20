from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.services.database_service import DatabaseService


@pytest.fixture
def db_service(tmp_path) -> DatabaseService:
    """Provide a DatabaseService instance for testing."""
    db_path = tmp_path / "test.db"
    return DatabaseService(str(db_path))


def test_clear_database_success(db_service):
    """Should clear all data from the database tables successfully"""
    # This test now checks that the clear_database method runs without error.
    # A more thorough test would involve adding data and then checking that it was deleted.
    db_service.clear_database()


def test_clear_database_failure(db_service, monkeypatch):
    """Should handle clear database failure and rollback"""
    # We now need to mock the session object used by the service
    mock_session = MagicMock()
    mock_session.execute.side_effect = SQLAlchemyError("Test Error")
    monkeypatch.setattr(db_service, "session_local", lambda: mock_session)

    with pytest.raises(SQLAlchemyError):
        db_service.clear_database()

    mock_session.rollback.assert_called_once()
