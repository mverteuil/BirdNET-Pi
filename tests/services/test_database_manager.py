from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from models.database_models import Detection
from services.database_manager import DatabaseManager


@pytest.fixture
def mock_db_path():
    return "/tmp/test_birdnetpi.db"


@pytest.fixture
def db_manager(mock_db_path):
    with (
        patch("services.database_manager.os.makedirs"),
        patch("services.database_manager.create_engine") as mock_create_engine,
        patch("services.database_manager.Base.metadata.create_all"),
        patch("services.database_manager.sessionmaker") as mock_sessionmaker,
    ):

        manager = DatabaseManager(db_path=mock_db_path)
        mock_engine_instance = MagicMock()
        mock_create_engine.return_value = mock_engine_instance
        mock_session_local_instance = MagicMock()
        mock_sessionmaker.return_value = mock_session_local_instance

        manager.initialize_database()
        yield manager


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def mock_session_local(mock_session):
    mock_session_local = MagicMock()
    mock_session_local.return_value = mock_session
    return mock_session_local


def test_initialize_database_success(db_manager, mock_db_path):
    """Should initialize the database successfully"""
    # The initialization is already done in the fixture, so we just assert its state
    assert db_manager.engine is not None
    assert db_manager.SessionLocal is not None


@patch("services.database_manager.create_engine", side_effect=SQLAlchemyError)
def test_initialize_database_failure(
    mock_create_engine,
    db_manager,
    capsys,
):
    """Should handle database initialization failure"""
    # Re-initialize to trigger the error path
    with pytest.raises(SQLAlchemyError):
        db_manager.initialize_database()
    captured = capsys.readouterr()
    assert "Error initializing database" in captured.out


def test_add_detection_success(db_manager, mock_session):
    """Should add a detection record successfully"""
    db_manager.SessionLocal.return_value = mock_session
    detection_data = {
        "species": "Test Species",
        "confidence": 0.9,
        "timestamp": "2023-01-01 12:00:00",
        "audio_file_path": "/path/to/audio.wav",
    }
    mock_detection_instance = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = (
        None  # Ensure no existing detection
    )
    mock_session.add.return_value = mock_detection_instance

    result = db_manager.add_detection(detection_data)

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()
    mock_session.close.assert_called_once()
    assert isinstance(result, Detection)  # Check if it returns a Detection object


def test_add_detection_failure(db_manager, mock_session, capsys):
    """Should handle add detection failure and rollback"""
    db_manager.SessionLocal.return_value = mock_session
    mock_session.add.side_effect = SQLAlchemyError("Test Error")
    detection_data = {
        "species": "Test Species",
        "confidence": 0.9,
        "timestamp": "2023-01-01 12:00:00",
        "audio_file_path": "/path/to/audio.wav",
    }

    with pytest.raises(SQLAlchemyError):
        db_manager.add_detection(detection_data)

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
    captured = capsys.readouterr()
    assert "Error adding detection" in captured.out


def test_get_all_detections_success(db_manager, mock_session):
    """Should retrieve all detection records successfully"""
    db_manager.SessionLocal.return_value = mock_session
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_session.query.return_value.all.return_value = mock_detections

    result = db_manager.get_all_detections()

    mock_session.query.assert_called_once_with(Detection)
    mock_session.query.return_value.all.assert_called_once()
    mock_session.close.assert_called_once()
    assert result == mock_detections


def test_get_all_detections_failure(db_manager, mock_session, capsys):
    """Should handle get all detections failure"""
    db_manager.SessionLocal.return_value = mock_session
    mock_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        db_manager.get_all_detections()

    mock_session.close.assert_called_once()
    captured = capsys.readouterr()
    assert "Error retrieving detections" in captured.out


def test_clear_database_success(db_manager, mock_session):
    """Should clear all data from the database tables successfully"""
    db_manager.SessionLocal.return_value = mock_session
    mock_session.execute.return_value = MagicMock()

    db_manager.clear_database()

    assert mock_session.execute.call_count == 2
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_clear_database_failure(db_manager, mock_session, capsys):
    """Should handle clear database failure and rollback"""
    db_manager.SessionLocal.return_value = mock_session
    mock_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        db_manager.clear_database()

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
    captured = capsys.readouterr()
    assert "Error clearing database" in captured.out
