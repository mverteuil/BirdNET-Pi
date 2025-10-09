"""Integration tests for DataManager - testing real database operations.

This file demonstrates the proper way to test DataManager:
- Uses real database with actual SQL queries
- Tests complete workflows, not mock configurations
- Verifies actual data persistence and retrieval
- Replaces mock-heavy tests with meaningful integration tests

Pattern:
    BEFORE (Mock-Heavy):
        - Mock all 6 dependencies
        - Configure mock return values
        - Assert mock returns what we configured
        - Tests nothing real (0 SQL executed)

    AFTER (Integration):
        - Use real database fixtures
        - Execute actual CRUD operations
        - Verify real data persistence
        - Tests actual workflows

See: test_data_manager.py for the problematic mock-heavy version
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from birdnetpi.detections.manager import DataManager
from birdnetpi.detections.models import Detection
from birdnetpi.system.file_manager import FileManager
from birdnetpi.web.core.container import Container


@pytest.fixture
async def data_manager_with_real_db(app_with_temp_data):
    """Create DataManager using the app's configured services.

    This approach reuses the test app's dependency injection container which
    already has proper database setup with temporary paths and overrides.
    """
    # Use the container's configured services (already has overrides from fixture)
    db_service = Container.core_database()
    species_db = Container.species_database()
    species_display = Container.species_display_service()
    query_service = Container.detection_query_service()
    path_resolver = Container.path_resolver()

    # Mock file manager to avoid actual file I/O
    mock_file_manager = MagicMock(spec=FileManager)
    mock_file_manager.save_detection_audio.return_value = Path("/fake/path/audio.wav")

    # Create DataManager with real database components
    manager = DataManager(
        database_service=db_service,
        species_database=species_db,
        species_display_service=species_display,
        detection_query_service=query_service,
        file_manager=mock_file_manager,
        path_resolver=path_resolver,
    )

    yield manager


class TestCRUDOperations:
    """Integration tests for basic CRUD operations with real database."""

    async def test_create_and_retrieve_detection(
        self, data_manager_with_real_db, app_with_temp_data, model_factory
    ):
        """Should create detection and retrieve it from real database."""
        # Get access to the app's database
        db_service = app_with_temp_data._test_db_service

        # Create a detection using the model factory
        new_detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
            timestamp=datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC),
        )

        # Persist to database
        async with db_service.get_async_db() as session:
            session.add(new_detection)
            await session.commit()
            await session.refresh(new_detection)
            detection_id = new_detection.id

        # Retrieve using DataManager
        retrieved = await data_manager_with_real_db.get_detection_by_id(detection_id)

        # Verify actual data was persisted and retrieved
        assert retrieved is not None
        assert retrieved.id == detection_id
        assert retrieved.scientific_name == "Turdus migratorius"
        assert retrieved.common_name == "American Robin"
        assert retrieved.confidence == 0.95

    async def test_update_detection_in_database(
        self, data_manager_with_real_db, app_with_temp_data, model_factory
    ):
        """Should update detection in real database and persist changes."""
        # Get access to the app's database
        db_service = app_with_temp_data._test_db_service

        # Create initial detection
        detection = model_factory.create_detection(
            scientific_name="Corvus brachyrhynchos",
            common_name="American Crow",
            confidence=0.88,
        )

        async with db_service.get_async_db() as session:
            session.add(detection)
            await session.commit()
            await session.refresh(detection)
            detection_id = detection.id

        # Update using DataManager
        updates = {"confidence": 0.95, "common_name": "Updated Crow Name"}
        updated = await data_manager_with_real_db.update_detection(detection_id, updates)

        # Verify updates persisted to database
        assert updated is not None
        assert updated.confidence == 0.95
        assert updated.common_name == "Updated Crow Name"

        # Verify by querying database directly
        async with db_service.get_async_db() as session:
            result = await session.execute(select(Detection).where(Detection.id == detection_id))
            from_db = result.scalar_one()
            assert from_db.confidence == 0.95
            assert from_db.common_name == "Updated Crow Name"

    async def test_delete_detection_from_database(
        self, data_manager_with_real_db, app_with_temp_data, model_factory
    ):
        """Should delete detection from real database."""
        # Get access to the app's database
        db_service = app_with_temp_data._test_db_service

        # Create detection to delete
        detection = model_factory.create_detection(
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
        )

        async with db_service.get_async_db() as session:
            session.add(detection)
            await session.commit()
            await session.refresh(detection)
            detection_id = detection.id

        # Delete using DataManager
        result = await data_manager_with_real_db.delete_detection(detection_id)
        assert result is True

        # Verify deletion by querying database with a fresh session
        # Use the DataManager's database service to ensure we're checking the same DB
        check_db_service = Container.core_database()
        async with check_db_service.get_async_db() as session:
            result = await session.execute(select(Detection).where(Detection.id == detection_id))
            assert result.scalar_one_or_none() is None

    async def test_get_all_detections_with_pagination(
        self, data_manager_with_real_db, app_with_temp_data, model_factory
    ):
        """Should retrieve paginated results from real database."""
        # Get access to the app's database
        db_service = app_with_temp_data._test_db_service

        # Create 5 detections
        async with db_service.get_async_db() as session:
            for i in range(5):
                detection = model_factory.create_detection(
                    scientific_name=f"Species {i}",
                    common_name=f"Bird {i}",
                    confidence=0.80 + (i * 0.02),
                )
                session.add(detection)
            await session.commit()

        # Test pagination with limit
        page1 = await data_manager_with_real_db.get_all_detections(limit=3, offset=0)
        page1_list = list(page1)
        assert len(page1_list) == 3

        # Test second page
        page2 = await data_manager_with_real_db.get_all_detections(limit=3, offset=3)
        page2_list = list(page2)
        assert len(page2_list) == 2  # Remaining detections


class TestEdgeCasesWithRealDatabase:
    """Integration tests for edge cases using real database."""

    async def test_update_nonexistent_detection(self, data_manager_with_real_db):
        """Should return None when updating detection that doesn't exist."""
        # Try to update non-existent detection
        fake_id = uuid4()
        result = await data_manager_with_real_db.update_detection(fake_id, {"confidence": 0.99})

        # Should return None, not raise error
        assert result is None

    async def test_delete_nonexistent_detection(self, data_manager_with_real_db):
        """Should return False when deleting detection that doesn't exist."""
        fake_id = uuid4()
        result = await data_manager_with_real_db.delete_detection(fake_id)

        # Should return False, not raise error
        assert result is False

    async def test_get_nonexistent_detection(self, data_manager_with_real_db):
        """Should return None when getting detection that doesn't exist."""
        fake_id = uuid4()
        result = await data_manager_with_real_db.get_detection_by_id(fake_id)

        # Should return None, not raise error
        assert result is None


class TestAudioFileOperations:
    """Integration tests for AudioFile operations with real database."""

    async def test_get_audio_file_by_path(
        self, data_manager_with_real_db, app_with_temp_data, model_factory
    ):
        """Should retrieve audio file by path from real database."""
        # Get access to the app's database
        db_service = app_with_temp_data._test_db_service

        # Create audio file
        audio_file = model_factory.create_audio_file(
            file_path=Path("/test/path/audio.wav"),
        )

        async with db_service.get_async_db() as session:
            session.add(audio_file)
            await session.commit()
            await session.refresh(audio_file)
            audio_file_id = audio_file.id

        # Retrieve using DataManager
        retrieved = await data_manager_with_real_db.get_audio_file_by_path(
            Path("/test/path/audio.wav")
        )

        # Verify actual data
        assert retrieved is not None
        assert retrieved.id == audio_file_id
        assert str(retrieved.file_path) == "/test/path/audio.wav"

    async def test_get_nonexistent_audio_file(self, data_manager_with_real_db):
        """Should return None for non-existent audio file path."""
        result = await data_manager_with_real_db.get_audio_file_by_path(
            Path("/nonexistent/audio.wav")
        )
        assert result is None


# Note: create_detection() test excluded because it requires file I/O infrastructure
"""
TESTS REQUIRING FILE I/O INFRASTRUCTURE:

test_create_detection_with_audio():
    - DataManager.create_detection() saves audio files to disk
    - Requires FileManager to be fully functional or mocked properly
    - Requires recordings directory structure
    - Future work: Set up temp directory infrastructure or enhanced mocking
"""
