"""Test the new database integration fixtures.

This file demonstrates and validates the async_in_memory_session and
populated_test_db fixtures that enable real database testing.
"""

from sqlalchemy import select

from birdnetpi.detections.models import AudioFile, Detection
from birdnetpi.location.models import Weather


class TestAsyncInMemorySession:
    """Test the async_in_memory_session fixture."""

    async def test_creates_all_tables(self, async_in_memory_session):
        """Should create all SQLModel tables in the in-memory database."""
        # Verify we can query tables (would fail if tables don't exist)
        result = await async_in_memory_session.execute(select(Detection))
        detections = result.scalars().all()
        assert detections == []  # Empty at start

        result = await async_in_memory_session.execute(select(AudioFile))
        audio_files = result.scalars().all()
        assert audio_files == []

        result = await async_in_memory_session.execute(select(Weather))
        weather_records = result.scalars().all()
        assert weather_records == []

    async def test_detection_persistence(self, async_in_memory_session, model_factory):
        """Should persist detections to the database and retrieve them."""
        # Create and persist a detection
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.95,
        )
        async_in_memory_session.add(detection)
        await async_in_memory_session.commit()

        # Verify it persisted by querying
        result = await async_in_memory_session.execute(
            select(Detection).where(Detection.scientific_name == "Turdus migratorius")
        )
        found = result.scalar_one()

        assert found.scientific_name == "Turdus migratorius"
        assert found.common_name == "American Robin"
        assert found.confidence == 0.95

    async def test_transaction_rollback(self, async_in_memory_session, model_factory):
        """Should support transaction rollback."""
        # Create detection but don't commit
        detection = model_factory.create_detection(
            scientific_name="Corvus brachyrhynchos",
            common_name="American Crow",
        )
        async_in_memory_session.add(detection)

        # Rollback instead of commit
        await async_in_memory_session.rollback()

        # Verify nothing was persisted
        result = await async_in_memory_session.execute(select(Detection))
        detections = result.scalars().all()
        assert len(detections) == 0

    async def test_relationship_queries(self, async_in_memory_session, model_factory):
        """Should support querying relationships between models."""
        # Create audio file
        audio_file = model_factory.create_audio_file()
        async_in_memory_session.add(audio_file)
        await async_in_memory_session.commit()
        await async_in_memory_session.refresh(audio_file)

        # Create detection linked to audio file
        detection = model_factory.create_detection(
            scientific_name="Cardinalis cardinalis",
            audio_file_id=audio_file.id,
        )
        async_in_memory_session.add(detection)
        await async_in_memory_session.commit()

        # Query detection and verify relationship
        result = await async_in_memory_session.execute(
            select(Detection).where(Detection.scientific_name == "Cardinalis cardinalis")
        )
        found = result.scalar_one()
        assert found.audio_file_id == audio_file.id


class TestPopulatedTestDB:
    """Test the populated_test_db fixture."""

    async def test_has_three_detections(self, populated_test_db):
        """Should pre-populate database with 3 known detections."""
        result = await populated_test_db.execute(select(Detection))
        detections = result.scalars().all()

        assert len(detections) == 3

        # Verify known species
        species = {d.common_name for d in detections}
        assert species == {"American Robin", "American Crow", "Northern Cardinal"}

    async def test_has_known_robin_detection(self, populated_test_db):
        """Should have robin detection with known confidence."""
        result = await populated_test_db.execute(
            select(Detection).where(Detection.common_name == "American Robin")
        )
        robin = result.scalar_one()

        assert robin.scientific_name == "Turdus migratorius"
        assert robin.confidence == 0.95
        assert robin.audio_file_id is not None

    async def test_has_audio_files(self, populated_test_db):
        """Should pre-populate with 2 audio files."""
        result = await populated_test_db.execute(select(AudioFile))
        audio_files = result.scalars().all()

        assert len(audio_files) == 2

    async def test_has_weather_data(self, populated_test_db):
        """Should pre-populate with weather record."""
        result = await populated_test_db.execute(select(Weather))
        weather_records = result.scalars().all()

        assert len(weather_records) == 1

        weather = weather_records[0]
        assert weather.temperature == 15.0
        assert weather.humidity == 60.0

    async def test_can_add_more_data(self, populated_test_db, model_factory):
        """Should allow adding more data to populated database."""
        # Add a 4th detection
        new_detection = model_factory.create_detection(
            scientific_name="Cyanocitta cristata",
            common_name="Blue Jay",
            confidence=0.87,
        )
        populated_test_db.add(new_detection)
        await populated_test_db.commit()

        # Verify we now have 4
        result = await populated_test_db.execute(select(Detection))
        detections = result.scalars().all()
        assert len(detections) == 4

    async def test_query_by_confidence_threshold(self, populated_test_db):
        """Should support filtering by confidence (realistic test scenario)."""
        # Query detections with confidence >= 0.90
        result = await populated_test_db.execute(
            select(Detection).where(Detection.confidence >= 0.90)
        )
        high_confidence = result.scalars().all()

        assert len(high_confidence) == 2  # Robin (0.95) and Cardinal (0.92)

        species = {d.common_name for d in high_confidence}
        assert species == {"American Robin", "Northern Cardinal"}
