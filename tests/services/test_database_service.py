from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.models.database_models import Detection
from birdnetpi.services.database_service import DatabaseService


@pytest.fixture
def mock_session():
    """Provide a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_session_local(mock_session) -> MagicMock:
    """Provide a mock SQLAlchemy sessionmaker that returns a mock session."""
    mock_session_local = MagicMock()
    mock_session_local.return_value = mock_session
    return mock_session_local


@pytest.fixture
def db_service(mock_session_local) -> DatabaseService:
    """Provide a DatabaseService instance for testing."""
    return DatabaseService(mock_session_local)


@pytest.fixture
def mock_csv_file(tmp_path) -> str:
    """Provide a mock CSV file for testing database import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;0.9;1.0;2.0;0.5;1;1.0;0.0\n"
        "2023-01-02;11:00:00;SciName2;ComName2;0.8;3.0;4.0;0.6;2;1.1;0.1\n"
    )
    csv_path = tmp_path / "test_detections.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)





def test_clear_database_success(db_service, mock_session):
    """Should clear all data from the database tables successfully"""
    db_service.clear_database()

    assert mock_session.execute.call_count == len(Detection.metadata.sorted_tables)
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_clear_database_failure(db_service, mock_session, capsys):
    """Should handle clear database failure and rollback"""
    mock_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        db_service.clear_database()

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
    captured = capsys.readouterr()
    assert "Error clearing database" in captured.out





















