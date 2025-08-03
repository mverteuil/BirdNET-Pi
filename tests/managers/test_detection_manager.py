from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.services.database_service import DatabaseService


@pytest.fixture
def detection_manager():
    """Provide a DetectionManager instance with a mocked DatabaseService."""
    mock_db_service = MagicMock(spec=DatabaseService)
    manager = DetectionManager(db_service=mock_db_service)
    return manager


@pytest.fixture
def mock_csv_file(tmp_path):
    """Provide a mock CSV file for testing database import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;0.9;1.0;2.0;0.5;1;1.0;0.0\n"
        "2023-01-02;11:00:00;SciName2;ComName2;0.8;3.0;4.0;0.6;2;1.1;0.1\n"
    )
    csv_path = tmp_path / "test_detections.csv"
    csv_path.write_text(csv_content)
    return str(csv_path)


def test_create_detection_success(detection_manager):
    """Should create a detection record and associated audio file successfully"""
    detection_event = DetectionEvent(
        species_tensor="Turdus migratorius_Test Species",
        scientific_name="Turdus migratorius",
        common_name_tensor="Test Species",
        confidence=0.9,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        audio_file_path="/path/to/audio.wav",
        duration=10.0,
        size_bytes=1024,
        recording_start_time=datetime(2023, 1, 1, 11, 59, 50),
    )
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)

    mock_db_session.add.side_effect = [None, None]  # For audio_file and detection
    mock_db_session.flush.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = mock_detection

    result = detection_manager.create_detection(detection_event)
    mock_db_session.commit.assert_called_once()
    assert isinstance(result, Detection)


def test_create_detection_failure(detection_manager):
    """Should handle create detection failure"""
    detection_event = DetectionEvent(
        species_tensor="Turdus migratorius_Test Species",
        scientific_name="Turdus migratorius",
        common_name_tensor="Test Species",
        confidence=0.9,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        audio_file_path="/path/to/audio.wav",
        duration=10.0,
        size_bytes=1024,
        recording_start_time=datetime(2023, 1, 1, 11, 59, 50),
    )
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.add.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.create_detection(detection_event)

    mock_db_session.rollback.assert_called_once()


def test_get_all_detections_success(detection_manager):
    """Should retrieve all detection records successfully"""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_db_session.query.return_value.all.return_value = mock_detections

    result = detection_manager.get_all_detections()

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.all.assert_called_once()
    assert result == mock_detections


def test_get_all_detections_failure(detection_manager):
    """Should handle get all detections failure"""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_all_detections()

    mock_db_session.rollback.assert_called_once()


def test_import_detections_from_csv_success(detection_manager, mock_csv_file):
    """Should import detection records from a CSV file successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session

    detection_manager.import_detections_from_csv(mock_csv_file)

    # Assertions for the first detection
    # Check the AudioFile object added
    audio_file_call_1 = mock_db_session.add.call_args_list[0]
    audio_file_obj_1 = audio_file_call_1.args[0]
    assert isinstance(audio_file_obj_1, AudioFile)
    assert audio_file_obj_1.file_path == "csv_import_20230101100000.wav"
    assert audio_file_obj_1.duration == 0.0
    assert audio_file_obj_1.size_bytes == 0
    assert audio_file_obj_1.recording_start_time == datetime(2023, 1, 1, 10, 0, 0)

    # Check the Detection object added
    detection_call_1 = mock_db_session.add.call_args_list[1]
    detection_obj_1 = detection_call_1.args[0]
    assert isinstance(detection_obj_1, Detection)
    assert detection_obj_1.species == "ComName1 (SciName1)"
    assert detection_obj_1.confidence == 0.9
    assert detection_obj_1.timestamp == datetime(2023, 1, 1, 10, 0, 0)
    assert detection_obj_1.latitude == 1.0
    assert detection_obj_1.longitude == 2.0
    assert detection_obj_1.cutoff == 0.5
    assert detection_obj_1.week == 1
    assert detection_obj_1.sensitivity == 1.0
    assert detection_obj_1.overlap == 0.0
    assert detection_obj_1.audio_file_id == audio_file_obj_1.id  # Should be linked

    # Assertions for the second detection
    audio_file_call_2 = mock_db_session.add.call_args_list[2]
    audio_file_obj_2 = audio_file_call_2.args[0]
    assert isinstance(audio_file_obj_2, AudioFile)
    assert audio_file_obj_2.file_path == "csv_import_20230102110000.wav"
    assert audio_file_obj_2.duration == 0.0
    assert audio_file_obj_2.size_bytes == 0
    assert audio_file_obj_2.recording_start_time == datetime(2023, 1, 2, 11, 0, 0)

    detection_call_2 = mock_db_session.add.call_args_list[3]
    detection_obj_2 = detection_call_2.args[0]
    assert isinstance(detection_obj_2, Detection)
    assert detection_obj_2.species == "ComName2 (SciName2)"
    assert detection_obj_2.confidence == 0.8
    assert detection_obj_2.timestamp == datetime(2023, 1, 2, 11, 0, 0)
    assert detection_obj_2.latitude == 3.0
    assert detection_obj_2.longitude == 4.0
    assert detection_obj_2.cutoff == 0.6
    assert detection_obj_2.week == 2
    assert detection_obj_2.sensitivity == 1.1
    assert detection_obj_2.overlap == 0.1
    assert detection_obj_2.audio_file_id == audio_file_obj_2.id  # Should be linked

    mock_db_session.flush.assert_called()  # Called twice, once for each AudioFile
    mock_db_session.commit.assert_called_once()
    assert mock_db_session.add.call_count == 4  # Two AudioFile, two Detection


def test_import_detections_from_csv_file_not_found(detection_manager):
    """Should handle FileNotFoundError when CSV file is not found."""
    detection_manager.db_service.get_db.return_value.__enter__.side_effect = FileNotFoundError(
        "File not found"
    )

    with pytest.raises(FileNotFoundError):
        detection_manager.import_detections_from_csv("/nonexistent/path/to/file.csv")


def test_import_detections_from_csv_value_error(detection_manager, tmp_path):
    """Should handle ValueError during data conversion in CSV import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;not_a_float;1.0;2.0;0.5;1;1.0;0.0\n"
    )
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(csv_content)

    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session

    detection_manager.import_detections_from_csv(str(csv_path))

    mock_db_session.add.assert_called_once()
    assert isinstance(mock_db_session.add.call_args[0][0], AudioFile)
    mock_db_session.commit.assert_called_once()


def test_import_detections_from_csv_unpacking_value_error(detection_manager, tmp_path):
    """Should handle ValueError due to unpacking error in CSV import."""
    csv_content = (
        "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n"
        "2023-01-01;10:00:00;SciName1;ComName1;0.9\n"
    )  # Missing columns
    csv_path = tmp_path / "missing_cols.csv"
    csv_path.write_text(csv_content)

    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session

    detection_manager.import_detections_from_csv(str(csv_path))

    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_called_once()


def test_import_detections_from_csv_sqlalchemy_error(detection_manager, mock_csv_file):
    """Should handle SQLAlchemyError during CSV import and rollback."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.commit.side_effect = SQLAlchemyError("DB Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.import_detections_from_csv(mock_csv_file)

    mock_db_session.rollback.assert_called_once()


def test_get_detection_success(detection_manager):
    """Should retrieve a detection record successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.query.return_value.get.return_value = mock_detection

    result = detection_manager.get_detection(1)

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.get.assert_called_once_with(1)
    assert result == mock_detection


def test_get_detection_failure(detection_manager):
    """Should handle get detection failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detection(1)

    mock_db_session.rollback.assert_called_once()


def test_delete_detection_success(detection_manager):
    """Should delete a detection record successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.query.return_value.get.return_value = mock_detection

    detection_manager.delete_detection(1)

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.get.assert_called_once_with(1)
    mock_db_session.delete.assert_called_once_with(mock_detection)
    mock_db_session.commit.assert_called_once()


def test_delete_detection_failure(detection_manager):
    """Should handle delete detection failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.delete_detection(1)

    mock_db_session.rollback.assert_called_once()


def test_get_detections_by_species_success(detection_manager):
    """Should retrieve all detection records for a species successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_db_session.query.return_value.filter_by.return_value.all.return_value = mock_detections

    result = detection_manager.get_detections_by_species("Test Species")

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.filter_by.assert_called_once_with(species="Test Species")
    mock_db_session.query.return_value.filter_by.return_value.all.assert_called_once()
    assert result == mock_detections


def test_get_detections_by_species_failure(detection_manager):
    """Should handle get detections by species failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detections_by_species("Test Species")

    mock_db_session.rollback.assert_called_once()


def test_get_detection_counts_by_date_range_success(detection_manager):
    """Should retrieve detection counts by date range successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.return_value.filter.return_value.count.side_effect = [10, 5]
    (
        mock_db_session.query.return_value.filter.return_value.distinct.return_value.count.return_value
    ) = 5

    result = detection_manager.get_detection_counts_by_date_range(
        datetime(2023, 1, 1), datetime(2023, 1, 31)
    )

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called twice for total_count and unique_species_count
    assert result == {"total_count": 10, "unique_species": 5}


def test_get_detection_counts_by_date_range_failure(detection_manager):
    """Should handle get detection counts by date range failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detection_counts_by_date_range(
            datetime(2023, 1, 1), datetime(2023, 1, 31)
        )

    mock_db_session.rollback.assert_called_once()


def test_get_top_species_with_prior_counts_success(detection_manager):
    """Should retrieve top species with prior counts successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    (mock_db_session.query().outerjoin().order_by().limit().all.return_value) = [
        MagicMock(species="species1", current_count=10, prior_count=5),
        MagicMock(species="species2", current_count=8, prior_count=2),
    ]

    result = detection_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called multiple times for subqueries and main query
    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_top_species_with_prior_counts_failure(detection_manager):
    """Should handle get top species with prior counts failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_top_species_with_prior_counts(
            datetime(2023, 1, 1),
            datetime(2023, 1, 31),
            datetime(2022, 12, 1),
            datetime(2022, 12, 31),
        )

    mock_db_session.rollback.assert_called_once()


def test_get_new_species_data_success(detection_manager):
    """Should retrieve new species data successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    (mock_db_session.query().filter().distinct().subquery().return_value) = MagicMock()
    (mock_db_session.query().filter().group_by().order_by().all.return_value) = [
        MagicMock(species="species1", count=10),
        MagicMock(species="species2", count=8),
    ]

    result = detection_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called multiple times for subquery and main query
    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_new_species_data_failure(detection_manager):
    """Should handle get new species data failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    mock_db_session.rollback.assert_called_once()


def test_get_most_recent_detections_success(detection_manager):
    """Should retrieve most recent detections successfully."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_detection.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection.species = "Common Blackbird (Turdus merula)"
    mock_detection.confidence = 0.9
    mock_detection.latitude = 1.0
    mock_detection.longitude = 2.0
    mock_detection.cutoff = 0.5
    mock_detection.week = 1
    mock_detection.sensitivity = 1.0
    mock_detection.overlap = 0.0
    mock_db_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = [
        mock_detection
    ]

    result = detection_manager.get_most_recent_detections(1)

    detection_manager.db_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.order_by.assert_called_once()
    mock_db_session.query.return_value.order_by.return_value.limit.assert_called_once_with(1)
    mock_db_session.query.return_value.order_by.return_value.limit.return_value.all.assert_called_once()
    assert len(result) == 1
    assert result[0]["Com_Name"] == "Common Blackbird"
    assert result[0]["Sci_Name"] == "Turdus merula"


def test_get_most_recent_detections_failure(detection_manager):
    """Should handle get most recent detections failure."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_most_recent_detections(1)

    mock_db_session.rollback.assert_called_once()


def test_get_best_detections_success(detection_manager):
    """Should retrieve the best detection for each species, sorted by confidence."""
    mock_db_session = MagicMock()
    detection_manager.db_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Create multiple mock detections with varying confidence levels for each species
    mock_cardinal_high = MagicMock(spec=Detection)
    mock_cardinal_high.id = 1
    mock_cardinal_high.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_cardinal_high.species = "Northern Cardinal (Cardinalis cardinalis)"
    mock_cardinal_high.confidence = 0.95

    mock_cardinal_low = MagicMock(spec=Detection)
    mock_cardinal_low.id = 2
    mock_cardinal_low.timestamp.strftime.side_effect = ["2023-01-01", "12:01:00"]
    mock_cardinal_low.species = "Northern Cardinal (Cardinalis cardinalis)"
    mock_cardinal_low.confidence = 0.85

    mock_robin_high = MagicMock(spec=Detection)
    mock_robin_high.id = 3
    mock_robin_high.timestamp.strftime.side_effect = ["2023-01-02", "14:00:00"]
    mock_robin_high.species = "American Robin (Turdus migratorius)"
    mock_robin_high.confidence = 0.9

    mock_robin_low = MagicMock(spec=Detection)
    mock_robin_low.id = 4
    mock_robin_low.timestamp.strftime.side_effect = ["2023-01-02", "14:01:00"]
    mock_robin_low.species = "American Robin (Turdus migratorius)"
    mock_robin_low.confidence = 0.8

    # Mock the final query to return the best detection for each species
    (mock_db_session.query().filter().order_by().limit().all.return_value) = [
        mock_cardinal_high,
        mock_robin_high,
    ]

    result = detection_manager.get_best_detections(2)

    # Assertions
    assert len(result) == 2
    assert result[0]["Confidence"] == 0.95
    assert result[1]["Confidence"] == 0.9
    assert result[0]["Com_Name"] == "Northern Cardinal"
    assert result[1]["Com_Name"] == "American Robin"
