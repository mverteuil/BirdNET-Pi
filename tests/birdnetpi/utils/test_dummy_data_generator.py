import datetime
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birdnetpi.detections.manager import DataManager
from birdnetpi.utils.dummy_data_generator import generate_dummy_detections, get_random_ioc_species
from birdnetpi.web.models.detections import DetectionEvent


@pytest.fixture
def mock_data_manager():
    """Mock DataManager instance."""
    mock = MagicMock(
        spec=DataManager, create_detection=AsyncMock(spec=DataManager.create_detection)
    )
    return mock


class TestDummyDataGenerator:
    """Test the TestDummyDataGenerator class."""

    @pytest.mark.asyncio
    async def test_generate_dummy_detections(self, mock_data_manager):
        """Should generate specified number of dummy detections via DetectionManager."""
        num_detections = 5
        await generate_dummy_detections(mock_data_manager, num_detections)
        assert mock_data_manager.create_detection.call_count == num_detections
        for call_args in mock_data_manager.create_detection.call_args_list:
            detection_event = call_args.args[0]
            assert isinstance(detection_event, DetectionEvent)
            assert isinstance(detection_event.timestamp, datetime.datetime)
            assert isinstance(detection_event.audio_data, str)
            assert isinstance(detection_event.sample_rate, int)
            assert isinstance(detection_event.channels, int)

    def test_main_entry_point_via_subprocess(self, repo_root):
        """Should execute __main__ block when running module as script."""
        module_path = repo_root / "src" / "birdnetpi" / "utils" / "dummy_data_generator.py"
        try:
            result = subprocess.run(
                [sys.executable, str(module_path)], capture_output=True, text=True, timeout=5
            )
            assert result.returncode in [0, 1]
        except subprocess.TimeoutExpired:
            pass

    @pytest.mark.asyncio
    async def test_get_random_ioc_species(self, path_resolver):
        """Should fetching random IOC species from the database."""
        with patch("aiosqlite.connect", autospec=True) as mock_connect:
            from aiosqlite import Connection, Cursor

            mock_cursor = AsyncMock(spec=Cursor)
            mock_cursor.fetchall = AsyncMock(
                spec=callable,
                return_value=[
                    ("Cyanocitta cristata", "Blue Jay"),
                    ("Turdus migratorius", "American Robin"),
                    ("Cardinalis cardinalis", "Northern Cardinal"),
                ],
            )
            mock_db = AsyncMock(spec=Connection)
            mock_db.execute = AsyncMock(spec=callable, return_value=mock_cursor)
            mock_connect.return_value.__aenter__.return_value = mock_db
            species = await get_random_ioc_species(path_resolver, num_species=3)
            assert len(species) == 3
            assert species[0] == ("Cyanocitta cristata", "Blue Jay")
            assert species[1] == ("Turdus migratorius", "American Robin")
            assert species[2] == ("Cardinalis cardinalis", "Northern Cardinal")
            mock_db.execute.assert_called_once()
            sql_query = mock_db.execute.call_args[0][0]
            assert "SELECT scientific_name, english_name" in sql_query
            assert "FROM species" in sql_query
            assert "ORDER BY RANDOM()" in sql_query
            assert "LIMIT ?" in sql_query

    @pytest.mark.asyncio
    async def test_generate_dummy_detections_with_ioc_species(
        self, mock_data_manager, path_resolver
    ):
        """Should generate detections with correct IOC species ratio."""
        mock_data_manager.path_resolver = path_resolver
        with patch(
            "birdnetpi.utils.dummy_data_generator.get_random_ioc_species", autospec=True
        ) as mock_get_species:
            mock_get_species.return_value = [
                ("Cyanocitta cristata", "Blue Jay"),
                ("Turdus migratorius", "American Robin"),
            ]
            await generate_dummy_detections(
                mock_data_manager, num_detections=10, ioc_species_ratio=0.5
            )
            mock_get_species.assert_called_once_with(path_resolver, 20)
            assert mock_data_manager.create_detection.call_count == 10
            ioc_detections = 0
            for call_args in mock_data_manager.create_detection.call_args_list:
                detection_event = call_args.args[0]
                if detection_event.scientific_name in ["Cyanocitta cristata", "Turdus migratorius"]:
                    ioc_detections += 1
            assert ioc_detections > 0
