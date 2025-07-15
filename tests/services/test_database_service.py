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


def test_import_detections_from_csv_success(
    db_service, mock_session, mock_csv_file, capsys
):
    """Should import detection records from a CSV file successfully."""
    db_service.import_detections_from_csv(mock_csv_file)

    assert mock_session.add.call_count == 2
    assert mock_session.commit.call_count == 1
    captured = capsys.readouterr()
    assert "Successfully imported detections" in captured.out
    mock_session.close.assert_called_once()


def test_import_detections_from_csv_file_not_found(db_service, capsys):
    """Should handle FileNotFoundError when CSV file is not found."""
    db_service.import_detections_from_csv("/nonexistent/path/to/file.csv")
    captured = capsys.readouterr()
    assert "CSV file not found" in captured.out


def test_import_detections_from_csv_value_error(
    db_service, mock_session, tmp_path, capsys
):
    """Should handle ValueError during data conversion in CSV import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;not_a_float;1.0;2.0;0.5;1;1.0;0.0\n"
    )
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(csv_content)

    db_service.import_detections_from_csv(str(csv_path))

    mock_session.add.assert_not_called()
    mock_session.commit.assert_called_once()
    captured = capsys.readouterr()
    assert "Skipping row due to data conversion error" in captured.out
    mock_session.close.assert_called_once()


def test_import_detections_from_csv_unpacking_value_error(
    db_service, mock_session, tmp_path, capsys
):
    """Should handle ValueError due to unpacking error in CSV import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;0.9\n"
    )  # Missing columns
    csv_path = tmp_path / "missing_cols.csv"
    csv_path.write_text(csv_content)

    db_service.import_detections_from_csv(str(csv_path))

    mock_session.add.assert_not_called()
    mock_session.commit.assert_called_once()
    captured = capsys.readouterr()
    assert "Skipping row due to data conversion error" in captured.out
    mock_session.close.assert_called_once()


def test_import_detections_from_csv_sqlalchemy_error(
    db_service, mock_session, mock_csv_file, capsys
):
    """Should handle SQLAlchemyError during CSV import and rollback."""
    mock_session.commit.side_effect = SQLAlchemyError("DB Error")

    with pytest.raises(SQLAlchemyError):
        db_service.import_detections_from_csv(mock_csv_file)

    mock_session.rollback.assert_called_once()
    captured = capsys.readouterr()
    assert "Error importing detections from CSV" in captured.out
    mock_session.close.assert_called_once()


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


def test_get_detection_success(db_service, mock_session):
    """Should retrieve a detection record successfully"""
    mock_detection = MagicMock(spec=Detection)
    mock_session.query.return_value.get.return_value = mock_detection

    result = db_service.get_detection(1)

    mock_session.query.assert_called_once_with(Detection)
    mock_session.query.return_value.get.assert_called_once_with(1)
    mock_session.close.assert_called_once()
    assert result == mock_detection


def test_delete_detection_success(db_service, mock_session):
    """Should delete a detection record successfully"""
    mock_detection = MagicMock(spec=Detection)
    mock_session.query.return_value.get.return_value = mock_detection

    db_service.delete_detection(1)

    mock_session.delete.assert_called_once_with(mock_detection)
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_get_detections_by_species_success(db_service, mock_session):
    """Should retrieve all detection records for a species successfully"""
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_session.query.return_value.filter_by.return_value.all.return_value = (
        mock_detections
    )

    result = db_service.get_detections_by_species("Test Species")

    mock_session.query.assert_called_once_with(Detection)
    mock_session.query.return_value.filter_by.assert_called_once_with(
        species="Test Species"
    )
    mock_session.query.return_value.filter_by.return_value.all.assert_called_once()
    mock_session.close.assert_called_once()
    assert result == mock_detections


def test_get_detection_counts_by_date_range_success(db_service, mock_session):
    """Should retrieve detection counts by date range successfully"""
    mock_session.query.return_value.filter.return_value.count.side_effect = [10, 5]
    mock_session.query.return_value.filter.return_value.distinct.return_value.count.return_value = (
        5
    )

    result = db_service.get_detection_counts_by_date_range("2023-01-01", "2023-01-31")

    assert result == {"total_count": 10, "unique_species": 5}


def test_get_top_species_with_prior_counts_success(db_service, mock_session):
    """Should retrieve top species with prior counts successfully"""
    mock_session.query.return_value.outerjoin.return_value.order_by.return_value.limit.return_value.all.return_value = [
        MagicMock(species="species1", current_count=10, prior_count=5),
        MagicMock(species="species2", current_count=8, prior_count=2),
    ]

    result = db_service.get_top_species_with_prior_counts(
        "2023-01-01", "2023-01-31", "2022-12-01", "2022-12-31"
    )

    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_new_species_data_success(db_service, mock_session):
    """Should retrieve new species data successfully"""
    mock_session.query.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = [
        MagicMock(species="species1", count=10),
        MagicMock(species="species2", count=8),
    ]

    result = db_service.get_new_species_data("2023-01-01", "2023-01-31")

    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_most_recent_detections_success(db_service, mock_session):
    """Should retrieve most recent detections successfully"""
    mock_detection = MagicMock(spec=Detection)
    mock_detection.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection.species = "Common Blackbird (Turdus merula)"
    mock_detection.latitude = 1.0
    mock_detection.longitude = 2.0
    mock_detection.cutoff = 0.5
    mock_detection.week = 1
    mock_detection.sensitivity = 1.0
    mock_detection.overlap = 0.0
    mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = [
        mock_detection
    ]

    result = db_service.get_most_recent_detections(1)

    assert len(result) == 1
    assert result[0]["Com_Name"] == "Common Blackbird"
    assert result[0]["Sci_Name"] == "Turdus merula"
