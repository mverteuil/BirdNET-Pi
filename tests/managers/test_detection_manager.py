from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.database_models import Detection
from birdnetpi.models.detection_event import DetectionEvent
from birdnetpi.services.database_service import DatabaseService


@pytest.fixture
def detection_manager():
    """Provide a DetectionManager instance with a mocked DatabaseService."""
    mock_bnp_database_service = MagicMock(spec=DatabaseService)
    manager = DetectionManager(bnp_database_service=mock_bnp_database_service)
    return manager


def test_create_detection(detection_manager):
    """Should create a detection record and associated audio file successfully"""
    detection_event = DetectionEvent(
        species_tensor="Turdus migratorius_Test Species",
        scientific_name="Turdus migratorius",
        common_name="Test Species",
        confidence=0.9,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        audio_file_path="/path/to/audio.wav",
        duration=10.0,
        size_bytes=1024,
        latitude=40.7128,
        longitude=-74.0060,
        species_confidence_threshold=0.1,
        week=1,
        sensitivity_setting=1.25,
        overlap=0.5,
    )
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
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
        common_name="Test Species",
        confidence=0.9,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        audio_file_path="/path/to/audio.wav",
        duration=10.0,
        size_bytes=1024,
        latitude=40.7128,
        longitude=-74.0060,
        species_confidence_threshold=0.1,
        week=1,
        sensitivity_setting=1.25,
        overlap=0.5,
    )
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.add.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.create_detection(detection_event)

    mock_db_session.rollback.assert_called_once()


def test_get_all_detections(detection_manager):
    """Should retrieve all detection records successfully"""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_db_session.query.return_value.all.return_value = mock_detections

    result = detection_manager.get_all_detections()

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.all.assert_called_once()
    assert result == mock_detections


def test_get_all_detections_failure(detection_manager):
    """Should handle get all detections failure"""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_all_detections()

    mock_db_session.rollback.assert_called_once()


def test_get_detection(detection_manager):
    """Should retrieve a detection record successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.query.return_value.get.return_value = mock_detection

    result = detection_manager.get_detection(1)

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.get.assert_called_once_with(1)
    assert result == mock_detection


def test_get_detection_failure(detection_manager):
    """Should handle get detection failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detection(1)

    mock_db_session.rollback.assert_called_once()


def test_delete_detection(detection_manager):
    """Should delete a detection record successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.query.return_value.get.return_value = mock_detection

    detection_manager.delete_detection(1)

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.get.assert_called_once_with(1)
    mock_db_session.delete.assert_called_once_with(mock_detection)
    mock_db_session.commit.assert_called_once()


def test_delete_detection_failure(detection_manager):
    """Should handle delete detection failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.delete_detection(1)

    mock_db_session.rollback.assert_called_once()


def test_get_detections_by_species(detection_manager):
    """Should retrieve all detection records for a species successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_db_session.query.return_value.filter_by.return_value.all.return_value = mock_detections

    result = detection_manager.get_detections_by_species("Test Species")

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.filter_by.assert_called_once_with(
        scientific_name="Test Species"
    )
    mock_db_session.query.return_value.filter_by.return_value.all.assert_called_once()
    assert result == mock_detections


def test_get_detections_by_species_failure(detection_manager):
    """Should handle get detections by species failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detections_by_species("Test Species")

    mock_db_session.rollback.assert_called_once()


def test_get_detection_counts_by_date_range(detection_manager):
    """Should retrieve detection counts by date range successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.return_value.filter.return_value.count.side_effect = [10, 5]
    (
        mock_db_session.query.return_value.filter.return_value.distinct.return_value.count.return_value
    ) = 5

    result = detection_manager.get_detection_counts_by_date_range(
        datetime(2023, 1, 1), datetime(2023, 1, 31)
    )

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called twice for total_count and unique_species_count
    assert result == {"total_count": 10, "unique_species": 5}


def test_get_detection_counts_by_date_range_failure(detection_manager):
    """Should handle get detection counts by date range failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_detection_counts_by_date_range(
            datetime(2023, 1, 1), datetime(2023, 1, 31)
        )

    mock_db_session.rollback.assert_called_once()


def test_get_top_species__prior_counts(detection_manager):
    """Should retrieve top species with prior counts successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    (mock_db_session.query().outerjoin().order_by().limit().all.return_value) = [
        (
            "species1",
            "Species One",
            10,
            5,
        ),  # scientific_name, common_name, current_count, prior_count
        (
            "species2",
            "Species Two",
            8,
            2,
        ),  # scientific_name, common_name, current_count, prior_count
    ]

    result = detection_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called multiple times for subqueries and main query
    assert len(result) == 2
    assert result[0]["scientific_name"] == "species1"


def test_get_top_species__prior_counts_failure(detection_manager):
    """Should handle get top species with prior counts failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_top_species_with_prior_counts(
            datetime(2023, 1, 1),
            datetime(2023, 1, 31),
            datetime(2022, 12, 1),
            datetime(2022, 12, 31),
        )

    mock_db_session.rollback.assert_called_once()


def test_get_new_species_data(detection_manager):
    """Should retrieve new species data successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    (mock_db_session.query().filter().distinct().subquery().return_value) = MagicMock()
    (mock_db_session.query().filter().group_by().order_by().all.return_value) = [
        ("species1", "Species One", 10),  # scientific_name, common_name, count
        ("species2", "Species Two", 8),  # scientific_name, common_name, count
    ]

    result = detection_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called()  # Called multiple times for subquery and main query
    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_new_species_data_failure(detection_manager):
    """Should handle get new species data failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    mock_db_session.rollback.assert_called_once()


def test_get_most_recent_detections(detection_manager):
    """Should retrieve most recent detections successfully."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_detection = MagicMock(spec=Detection)
    mock_detection.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection.species_tensor = "Turdus merula_Common Blackbird"
    mock_detection.scientific_name = "Turdus merula"
    mock_detection.common_name = "Common Blackbird"
    mock_detection.common_name = "Common Blackbird"
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

    detection_manager.bnp_database_service.get_db.assert_called_once_with()
    mock_db_session.query.assert_called_once_with(Detection)
    mock_db_session.query.return_value.order_by.assert_called_once()
    mock_db_session.query.return_value.order_by.return_value.limit.assert_called_once_with(1)
    mock_db_session.query.return_value.order_by.return_value.limit.return_value.all.assert_called_once()
    assert len(result) == 1
    assert result[0]["common_name"] == "Common Blackbird"
    assert result[0]["scientific_name"] == "Turdus merula"


def test_get_most_recent_detections_failure(detection_manager):
    """Should handle get most recent detections failure."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )
    mock_db_session.query.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        detection_manager.get_most_recent_detections(1)

    mock_db_session.rollback.assert_called_once()


def test_get_best_detections(detection_manager):
    """Should retrieve the best detection for each species, sorted by confidence."""
    mock_db_session = MagicMock()
    detection_manager.bnp_database_service.get_db.return_value.__enter__.return_value = (
        mock_db_session
    )

    # Create multiple mock detections with varying confidence levels for each species
    mock_cardinal_high = MagicMock(spec=Detection)
    mock_cardinal_high.id = 1
    mock_cardinal_high.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_cardinal_high.species_tensor = "Cardinalis cardinalis_Northern Cardinal"
    mock_cardinal_high.scientific_name = "Cardinalis cardinalis"
    mock_cardinal_high.common_name = "Northern Cardinal"
    mock_cardinal_high.common_name = "Northern Cardinal"
    mock_cardinal_high.confidence = 0.95

    mock_cardinal_low = MagicMock(spec=Detection)
    mock_cardinal_low.id = 2
    mock_cardinal_low.timestamp.strftime.side_effect = ["2023-01-01", "12:01:00"]
    mock_cardinal_low.species_tensor = "Cardinalis cardinalis_Northern Cardinal"
    mock_cardinal_low.scientific_name = "Cardinalis cardinalis"
    mock_cardinal_low.common_name = "Northern Cardinal"
    mock_cardinal_low.common_name = "Northern Cardinal"
    mock_cardinal_low.confidence = 0.85

    mock_robin_high = MagicMock(spec=Detection)
    mock_robin_high.id = 3
    mock_robin_high.timestamp.strftime.side_effect = ["2023-01-02", "14:00:00"]
    mock_robin_high.species_tensor = "Turdus migratorius_American Robin"
    mock_robin_high.scientific_name = "Turdus migratorius"
    mock_robin_high.common_name = "American Robin"
    mock_robin_high.common_name = "American Robin"
    mock_robin_high.confidence = 0.9

    mock_robin_low = MagicMock(spec=Detection)
    mock_robin_low.id = 4
    mock_robin_low.timestamp.strftime.side_effect = ["2023-01-02", "14:01:00"]
    mock_robin_low.species_tensor = "Turdus migratorius_American Robin"
    mock_robin_low.scientific_name = "Turdus migratorius"
    mock_robin_low.common_name = "American Robin"
    mock_robin_low.common_name = "American Robin"
    mock_robin_low.confidence = 0.8

    # Mock the final query to return the best detection for each species
    (mock_db_session.query().filter().order_by().limit().all.return_value) = [
        mock_cardinal_high,
        mock_robin_high,
    ]

    result = detection_manager.get_best_detections(2)

    # Assertions
    assert len(result) == 2
    assert result[0]["confidence"] == 0.95
    assert result[1]["confidence"] == 0.9
    assert result[0]["common_name"] == "Northern Cardinal"
    assert result[1]["common_name"] == "American Robin"
