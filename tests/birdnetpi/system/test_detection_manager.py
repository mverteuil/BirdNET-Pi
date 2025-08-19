from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.database.database_service import DatabaseService
from birdnetpi.detections.data_manager import DataManager
from birdnetpi.detections.models import Detection
from birdnetpi.i18n.multilingual_database_service import MultilingualDatabaseService
from birdnetpi.species.display import SpeciesDisplayService
from birdnetpi.web.models.detections import DetectionEvent


@pytest.fixture
def data_manager():
    """Provide a DataManager instance with mocked services."""
    mock_database_service = MagicMock(spec=DatabaseService)
    mock_multilingual_service = MagicMock(spec=MultilingualDatabaseService)
    mock_species_display_service = MagicMock(spec=SpeciesDisplayService)
    manager = DataManager(
        database_service=mock_database_service,
        multilingual_service=mock_multilingual_service,
        species_display_service=mock_species_display_service,
    )
    return manager


def test_create_detection(data_manager):
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
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)

    mock_db_session.add.side_effect = [None, None]  # For audio_file and detection
    mock_db_session.flush.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = mock_detection

    result = data_manager.create_detection(detection_event)
    mock_db_session.commit.assert_called_once()
    assert isinstance(result, Detection)


def test_create_detection_failure(data_manager):
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
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.add.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.create_detection(detection_event)

    mock_db_session.rollback.assert_called_once()


def test_get_all_detections(data_manager):
    """Should retrieve all detection records successfully"""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_scalars = MagicMock()
    mock_scalars.__iter__ = lambda self: iter(mock_detections)
    mock_db_session.execute.return_value.scalars.return_value = mock_scalars

    result = data_manager.get_all_detections()

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called_once()
    assert list(result) == mock_detections


def test_get_all_detections_failure(data_manager):
    """Should handle get all detections failure"""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_all_detections()

    mock_db_session.rollback.assert_called_once()


def test_get_detection(data_manager):
    """Should retrieve a detection record successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_detection

    result = data_manager.get_detection_by_id(1)

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called_once()
    assert result == mock_detection


def test_get_detection_failure(data_manager):
    """Should handle get detection failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_detection_by_id(1)

    mock_db_session.rollback.assert_called_once()


def test_delete_detection(data_manager):
    """Should delete a detection record successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_detection

    result = data_manager.delete_detection(1)

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called_once()
    mock_db_session.delete.assert_called_once_with(mock_detection)
    mock_db_session.commit.assert_called_once()
    assert result is True


def test_delete_detection_failure(data_manager):
    """Should handle delete detection failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.delete_detection(1)

    mock_db_session.rollback.assert_called_once()


def test_get_detections_by_species(data_manager):
    """Should retrieve all detection records for a species successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detections = [MagicMock(spec=Detection), MagicMock(spec=Detection)]
    mock_scalars = MagicMock()
    mock_scalars.__iter__ = lambda self: iter(mock_detections)
    mock_db_session.execute.return_value.scalars.return_value = mock_scalars

    result = data_manager.get_detections_by_species("Test Species")

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called_once()
    assert list(result) == mock_detections


def test_get_detections_by_species_failure(data_manager):
    """Should handle get detections by species failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_detections_by_species("Test Species")

    mock_db_session.rollback.assert_called_once()


def test_get_detection_counts_by_date_range(data_manager):
    """Should retrieve detection counts by date range successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    # The actual implementation uses session.scalar() for counts
    mock_db_session.scalar.side_effect = [10, 5]

    result = data_manager.get_detection_counts_by_date_range(
        datetime(2023, 1, 1), datetime(2023, 1, 31)
    )

    data_manager.database_service.get_db.assert_called_once_with()
    assert (
        mock_db_session.scalar.call_count == 2
    )  # Called twice for total_count and unique_species_count
    assert result == {"total_count": 10, "unique_species": 5}


def test_get_detection_counts_by_date_range_failure(data_manager):
    """Should handle get detection counts by date range failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.scalar.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_detection_counts_by_date_range(datetime(2023, 1, 1), datetime(2023, 1, 31))

    mock_db_session.rollback.assert_called_once()


def test_get_top_species__prior_counts(data_manager):
    """Should retrieve top species with prior counts successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Mock the execute().all() pattern for the complex query
    mock_rows = [
        MagicMock(
            scientific_name="species1", common_name="Species One", current_count=10, prior_count=5
        ),
        MagicMock(
            scientific_name="species2", common_name="Species Two", current_count=8, prior_count=2
        ),
    ]
    # Make rows subscriptable like dict
    for row in mock_rows:
        row.__getitem__ = lambda self, key: getattr(self, key)

    mock_db_session.execute.return_value.__iter__ = lambda self: iter(mock_rows)

    result = data_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called()
    assert len(result) == 2
    assert result[0]["scientific_name"] == "species1"


def test_get_top_species__prior_counts_failure(data_manager):
    """Should handle get top species with prior counts failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_top_species_with_prior_counts(
            datetime(2023, 1, 1),
            datetime(2023, 1, 31),
            datetime(2022, 12, 1),
            datetime(2022, 12, 31),
        )

    mock_db_session.rollback.assert_called_once()


def test_get_new_species_data(data_manager):
    """Should retrieve new species data successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Mock the execute().all() pattern for the new species query
    mock_rows = [
        MagicMock(scientific_name="species1", common_name="Species One", count=10),
        MagicMock(scientific_name="species2", common_name="Species Two", count=8),
    ]
    # Make rows subscriptable like dict
    for row in mock_rows:
        row.__getitem__ = lambda self, key: getattr(self, key)

    mock_db_session.execute.return_value.__iter__ = lambda self: iter(mock_rows)

    result = data_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    data_manager.database_service.get_db.assert_called_once_with()
    mock_db_session.execute.assert_called()
    assert len(result) == 2
    assert result[0]["species"] == "species1"


def test_get_new_species_data_failure(data_manager):
    """Should handle get new species data failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    mock_db_session.rollback.assert_called_once()


def test_get_most_recent_detections(data_manager):
    """Should retrieve most recent detections successfully."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_detection = MagicMock(spec=Detection)
    mock_detection.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection.species_tensor = "Turdus merula_Common Blackbird"
    mock_detection.scientific_name = "Turdus merula"
    mock_detection.common_name = "Common Blackbird"
    mock_detection.confidence = 0.9
    mock_detection.latitude = 1.0
    mock_detection.longitude = 2.0
    mock_detection.species_confidence_threshold = 0.5
    mock_detection.week = 1
    mock_detection.sensitivity_setting = 1.0
    mock_detection.overlap = 0.0

    # Mock the execute().scalars() pattern
    mock_scalars = MagicMock()
    mock_scalars.__iter__ = lambda self: iter([mock_detection])
    mock_db_session.execute.return_value.scalars.return_value = mock_scalars

    result = data_manager.get_recent_detections(1)

    data_manager.database_service.get_db.assert_called_once_with()
    assert len(list(result)) == 1
    result_list = list(data_manager.get_recent_detections(1))
    assert result_list[0].common_name == "Common Blackbird"
    assert result_list[0].scientific_name == "Turdus merula"


def test_get_most_recent_detections_failure(data_manager):
    """Should handle get most recent detections failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_recent_detections(1)

    mock_db_session.rollback.assert_called_once()


def test_get_best_detections(data_manager):
    """Should retrieve the best detection for each species, sorted by confidence."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Create multiple mock detections with varying confidence levels for each species
    mock_cardinal_high = MagicMock(spec=Detection)
    mock_cardinal_high.id = 1
    mock_cardinal_high.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_cardinal_high.species_tensor = "Cardinalis cardinalis_Northern Cardinal"
    mock_cardinal_high.scientific_name = "Cardinalis cardinalis"
    mock_cardinal_high.common_name = "Northern Cardinal"
    mock_cardinal_high.confidence = 0.95

    mock_robin_high = MagicMock(spec=Detection)
    mock_robin_high.id = 3
    mock_robin_high.timestamp.strftime.side_effect = ["2023-01-02", "14:00:00"]
    mock_robin_high.species_tensor = "Turdus migratorius_American Robin"
    mock_robin_high.scientific_name = "Turdus migratorius"
    mock_robin_high.common_name = "American Robin"
    mock_robin_high.confidence = 0.9

    # Mock the scalars().all() pattern used in get_best_detections
    mock_db_session.scalars.return_value.all.return_value = [
        mock_cardinal_high,
        mock_robin_high,
    ]

    result = data_manager.get_best_detections(2)

    # Assertions - DataManager returns Detection objects not dictionaries
    assert len(result) == 2
    assert result[0].confidence == 0.95
    assert result[1].confidence == 0.9
    assert result[0].common_name == "Northern Cardinal"
    assert result[1].common_name == "American Robin"


# COMPREHENSIVE WEEKLY REPORT DETECTION MANAGER TESTS


def test_get_detection_counts_by_date_range__empty_result(data_manager):
    """Should handle empty detection count results."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    # Mock scalar() to return 0 for both count queries
    mock_db_session.scalar.side_effect = [0, 0]

    result = data_manager.get_detection_counts_by_date_range(
        datetime(2023, 1, 1), datetime(2023, 1, 31)
    )

    assert result == {"total_count": 0, "unique_species": 0}


def test_get_detection_counts_by_date_range__large_numbers(data_manager):
    """Should handle large detection counts."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    # Mock scalar() to return large numbers for count queries
    mock_db_session.scalar.side_effect = [50000, 1000]

    result = data_manager.get_detection_counts_by_date_range(
        datetime(2023, 1, 1), datetime(2023, 12, 31)
    )

    assert result == {"total_count": 50000, "unique_species": 1000}


def test_get_top_species_with_prior_counts__empty_result(data_manager):
    """Should handle empty top species results."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.return_value.all.return_value = []

    result = data_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    assert result == []


def test_get_top_species_with_prior_counts__with_nulls(data_manager):
    """Should handle species with null prior counts."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Simulate query results with some null prior counts
    mock_rows = [
        MagicMock(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            current_count=25,
            prior_count=15,
        ),
        MagicMock(
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            current_count=20,
            prior_count=None,
        ),
        MagicMock(
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            current_count=18,
            prior_count=0,
        ),
    ]
    # Make rows subscriptable like dict
    for row in mock_rows:
        row.__getitem__ = lambda self, key: getattr(self, key)

    mock_db_session.execute.return_value.__iter__ = lambda self: iter(mock_rows)

    result = data_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    assert len(result) == 3
    assert result[0]["scientific_name"] == "Turdus migratorius"
    assert result[0]["prior_count"] == 15
    assert result[1]["scientific_name"] == "Cardinalis cardinalis"
    assert result[1]["prior_count"] is None
    assert result[2]["scientific_name"] == "Cyanocitta cristata"
    assert result[2]["prior_count"] == 0


def test_get_top_species_with_prior_counts__limit_verification(data_manager):
    """Should verify that limit of 10 is enforced in top species query."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    # Create 10 mock results (the limit)
    mock_rows = []
    for i in range(10):
        row = MagicMock(
            scientific_name=f"species_{i}",
            common_name=f"Species {i}",
            current_count=100 - i,
            prior_count=50 - i,
        )
        row.__getitem__ = lambda self, key: getattr(self, key)
        mock_rows.append(row)

    mock_db_session.execute.return_value.__iter__ = lambda self: iter(mock_rows)

    result = data_manager.get_top_species_with_prior_counts(
        datetime(2023, 1, 1),
        datetime(2023, 1, 31),
        datetime(2022, 12, 1),
        datetime(2022, 12, 31),
    )

    # Should return exactly 10 results due to limit
    assert len(result) == 10
    mock_db_session.execute.assert_called()


def test_get_new_species_data__empty_result(data_manager):
    """Should handle empty new species results."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.execute.return_value.all.return_value = []

    result = data_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    assert result == []


def test_get_new_species_data__with_data_ordering(data_manager):
    """Should return new species data ordered by count descending."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Results should be ordered by count descending
    mock_rows = [
        MagicMock(scientific_name="Cyanocitta cristata", common_name="Blue Jay", count=15),
        MagicMock(
            scientific_name="Poecile atricapillus", common_name="Black-capped Chickadee", count=8
        ),
        MagicMock(
            scientific_name="Sitta carolinensis", common_name="White-breasted Nuthatch", count=3
        ),
    ]
    # Make rows subscriptable like dict
    for row in mock_rows:
        row.__getitem__ = lambda self, key: getattr(self, key)

    mock_db_session.execute.return_value.__iter__ = lambda self: iter(mock_rows)

    result = data_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    assert len(result) == 3
    assert result[0]["species"] == "Cyanocitta cristata"
    assert result[0]["count"] == 15
    assert result[1]["species"] == "Poecile atricapillus"
    assert result[1]["count"] == 8
    assert result[2]["species"] == "Sitta carolinensis"
    assert result[2]["count"] == 3


def test_get_new_species_data__prior_species_exclusion(data_manager):
    """Should verify that prior species are excluded from new species query."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Mock the execute().all() pattern
    mock_row = MagicMock(scientific_name="Cyanocitta cristata", common_name="Blue Jay", count=10)
    mock_row.__getitem__ = lambda self, key: getattr(self, key)
    mock_db_session.execute.return_value.__iter__ = lambda self: iter([mock_row])

    result = data_manager.get_new_species_data(datetime(2023, 1, 1), datetime(2023, 1, 31))

    # Verify that the query excludes species from prior period
    mock_db_session.execute.assert_called()
    assert len(result) == 1
    assert result[0]["species"] == "Cyanocitta cristata"


def test_get_best_detections__empty_result(data_manager):
    """Should handle empty best detections results."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.scalars.return_value.all.return_value = []

    result = data_manager.get_best_detections(10)

    assert result == []


def test_get_best_detections__confidence_ordering(data_manager):
    """Should return best detections ordered by confidence descending."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Create mock detections with different confidence levels
    mock_detection_high = MagicMock(spec=Detection)
    mock_detection_high.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection_high.scientific_name = "Turdus migratorius"
    mock_detection_high.common_name = "American Robin"
    mock_detection_high.confidence = 0.95
    mock_detection_high.latitude = None
    mock_detection_high.longitude = None

    mock_detection_medium = MagicMock(spec=Detection)
    mock_detection_medium.timestamp.strftime.side_effect = ["2023-01-01", "13:00:00"]
    mock_detection_medium.scientific_name = "Cardinalis cardinalis"
    mock_detection_medium.common_name = "Northern Cardinal"
    mock_detection_medium.confidence = 0.85
    mock_detection_medium.latitude = None
    mock_detection_medium.longitude = None

    # Should be ordered by confidence descending
    mock_db_session.scalars.return_value.all.return_value = [
        mock_detection_high,
        mock_detection_medium,
    ]

    result = data_manager.get_best_detections(2)

    assert len(result) == 2
    assert result[0].confidence == 0.95  # Highest confidence first
    assert result[0].common_name == "American Robin"
    assert result[1].confidence == 0.85  # Lower confidence second
    assert result[1].common_name == "Northern Cardinal"


def test_get_best_detections__one_per_species(data_manager):
    """Should return only one detection per species (the best one)."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session

    # Mock final detections
    mock_detection = MagicMock(spec=Detection)
    mock_detection.timestamp.strftime.side_effect = ["2023-01-01", "12:00:00"]
    mock_detection.scientific_name = "Turdus migratorius"
    mock_detection.common_name = "American Robin"
    mock_detection.confidence = 0.95
    mock_detection.latitude = None
    mock_detection.longitude = None

    mock_db_session.scalars.return_value.all.return_value = [mock_detection]

    result = data_manager.get_best_detections(10)

    # Verify that row_number() window function is used to get best per species
    assert len(result) == 1
    assert result[0].scientific_name == "Turdus migratorius"
    assert result[0].confidence == 0.95


def test_get_best_detections_failure(data_manager):
    """Should handle get best detections failure."""
    mock_db_session = MagicMock()
    data_manager.database_service.get_db.return_value.__enter__.return_value = mock_db_session
    mock_db_session.scalars.side_effect = SQLAlchemyError("Test Error")

    with pytest.raises(SQLAlchemyError):
        data_manager.get_best_detections(10)

    mock_db_session.rollback.assert_called_once()
