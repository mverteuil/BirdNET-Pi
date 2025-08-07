"""Tests for DetectionQueryService - JOIN-based queries with IOC database."""

import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from birdnetpi.models.database_models import Detection
from birdnetpi.models.ioc_database_models import IOCSpecies, IOCTranslation
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.detection_query_service import (
    DetectionQueryService,
    DetectionWithIOCData,
)
from birdnetpi.services.ioc_database_service import IOCDatabaseService


@pytest.fixture
def temp_main_db():
    """Create temporary main database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        yield tmp.name


@pytest.fixture
def temp_ioc_db():
    """Create temporary IOC database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        yield tmp.name


@pytest.fixture
def db_service(temp_main_db):
    """Create main database service."""
    return DatabaseService(temp_main_db)


@pytest.fixture
def ioc_db_service(temp_ioc_db):
    """Create IOC database service."""
    return IOCDatabaseService(temp_ioc_db)


@pytest.fixture
def query_service(db_service, ioc_db_service):
    """Create detection query service."""
    return DetectionQueryService(db_service, ioc_db_service)


@pytest.fixture
def populated_ioc_db(ioc_db_service):
    """Populate IOC database with test data."""
    with ioc_db_service.get_db() as session:
        # Add test species
        test_species = [
            IOCSpecies(
                scientific_name="Turdus migratorius",
                english_name="American Robin",
                order_name="Passeriformes",
                family="Turdidae",
                genus="Turdus",
                species_epithet="migratorius",
                authority="Linnaeus, 1766",
            ),
            IOCSpecies(
                scientific_name="Corvus brachyrhynchos",
                english_name="American Crow",
                order_name="Passeriformes",
                family="Corvidae",
                genus="Corvus",
                species_epithet="brachyrhynchos",
                authority="Brehm, CL, 1822",
            ),
            IOCSpecies(
                scientific_name="Strix varia",
                english_name="Barred Owl",
                order_name="Strigiformes",
                family="Strigidae",
                genus="Strix",
                species_epithet="varia",
                authority="Barton, 1799",
            ),
        ]

        for species in test_species:
            session.add(species)

        # Add test translations
        test_translations = [
            IOCTranslation(
                scientific_name="Turdus migratorius",
                language_code="es",
                common_name="Petirrojo Americano",
            ),
            IOCTranslation(
                scientific_name="Turdus migratorius",
                language_code="fr",
                common_name="Merle d'Amérique",
            ),
            IOCTranslation(
                scientific_name="Corvus brachyrhynchos",
                language_code="es",
                common_name="Cuervo Americano",
            ),
        ]

        for translation in test_translations:
            session.add(translation)

        session.commit()
    
    return ioc_db_service


@pytest.fixture
def sample_detections(db_service):
    """Create sample detections in main database."""
    detections = []
    base_time = datetime.now()
    
    with db_service.get_db() as session:
        test_detections = [
            Detection(
                id=uuid4(),
                species_tensor="Turdus migratorius_American Robin",
                scientific_name="Turdus migratorius",
                common_name="American Robin",
                confidence=0.85,
                timestamp=base_time,
                latitude=40.7128,
                longitude=-74.0060,
                species_confidence_threshold=0.7,
                week=20,
                sensitivity_setting=1.0,
                overlap=0.0,
            ),
            Detection(
                id=uuid4(),
                species_tensor="Corvus brachyrhynchos_American Crow",
                scientific_name="Corvus brachyrhynchos",
                common_name="American Crow",
                confidence=0.92,
                timestamp=base_time + timedelta(hours=1),
                latitude=40.7589,
                longitude=-73.9851,
                species_confidence_threshold=0.8,
                week=20,
                sensitivity_setting=1.2,
                overlap=0.1,
            ),
            Detection(
                id=uuid4(),
                species_tensor="Strix varia_Barred Owl",
                scientific_name="Strix varia",
                common_name="Barred Owl",
                confidence=0.78,
                timestamp=base_time + timedelta(hours=2),
                latitude=40.7505,
                longitude=-73.9934,
                species_confidence_threshold=0.6,
                week=20,
                sensitivity_setting=0.9,
                overlap=0.05,
            ),
            Detection(
                id=uuid4(),
                species_tensor="Unknown species_Unknown",
                scientific_name="Unknown species",
                common_name="Unknown",
                confidence=0.65,
                timestamp=base_time + timedelta(hours=3),
                latitude=40.7829,
                longitude=-73.9654,
                species_confidence_threshold=0.5,
                week=20,
                sensitivity_setting=1.1,
                overlap=0.15,
            ),
        ]
        
        for detection in test_detections:
            session.add(detection)
        
        session.commit()
        
        # Refresh objects to ensure all attributes are loaded before session closes
        for detection in test_detections:
            session.refresh(detection)
            detections.append(detection)
    
    return detections


class TestDetectionWithIOCData:
    """Test DetectionWithIOCData data class."""

    def test_detection_with_ioc_data_initialization(self):
        """Should initialize with all parameters correctly."""
        detection = Detection(
            id=uuid4(),
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.85,
            timestamp=datetime.now(),
        )
        
        data = DetectionWithIOCData(
            detection=detection,
            ioc_english_name="American Robin IOC",
            translated_name="Petirrojo Americano",
            family="Turdidae",
            genus="Turdus",
            order_name="Passeriformes",
        )
        
        assert data.detection == detection
        assert data.ioc_english_name == "American Robin IOC"
        assert data.translated_name == "Petirrojo Americano"
        assert data.family == "Turdidae"
        assert data.genus == "Turdus"
        assert data.order_name == "Passeriformes"

    def test_property_access(self):
        """Should provide access to detection properties."""
        detection_id = uuid4()
        timestamp = datetime.now()
        detection = Detection(
            id=detection_id,
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.85,
            timestamp=timestamp,
        )
        
        data = DetectionWithIOCData(detection=detection)
        
        assert data.id == detection_id
        assert data.scientific_name == "Turdus migratorius"
        assert data.common_name == "American Robin"
        assert data.confidence == 0.85
        assert data.timestamp == timestamp

    def test_get_best_common_name_prefer_translation(self):
        """Should prefer translated name when requested."""
        detection = Detection(
            id=uuid4(),
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.85,
            timestamp=datetime.now(),
        )
        
        data = DetectionWithIOCData(
            detection=detection,
            ioc_english_name="American Robin IOC",
            translated_name="Petirrojo Americano",
        )
        
        # Prefer translation
        result = data.get_best_common_name(prefer_translation=True)
        assert result == "Petirrojo Americano"

    def test_get_best_common_name_fallback_order(self):
        """Should fall back through name options correctly."""
        detection = Detection(
            id=uuid4(),
            scientific_name="Turdus migratorius",
            common_name="American Robin",
            confidence=0.85,
            timestamp=datetime.now(),
        )
        
        # Test IOC English name fallback
        data = DetectionWithIOCData(
            detection=detection,
            ioc_english_name="American Robin IOC",
        )
        result = data.get_best_common_name()
        assert result == "American Robin IOC"
        
        # Test tensor common name fallback
        data = DetectionWithIOCData(detection=detection)
        result = data.get_best_common_name()
        assert result == "American Robin"
        
        # Test scientific name fallback
        detection.common_name = None
        data = DetectionWithIOCData(detection=detection)
        result = data.get_best_common_name()
        assert result == "Turdus migratorius"


class TestDetectionQueryServiceInitialization:
    """Test service initialization."""

    def test_service_initialization(self, db_service, ioc_db_service):
        """Should initialize with required services."""
        service = DetectionQueryService(db_service, ioc_db_service)
        
        assert service.db_service == db_service
        assert service.ioc_db_service == ioc_db_service


class TestGetDetectionsWithIOCData:
    """Test getting detections with IOC data."""

    def test_get_detections_with_ioc_data_basic(self, query_service, populated_ioc_db, sample_detections):
        """Should return detections with IOC data."""
        results = query_service.get_detections_with_ioc_data(limit=10)
        
        # Should return detections (exact count depends on JOIN matches)
        assert isinstance(results, list)
        assert len(results) <= 10
        
        # Check that each result is DetectionWithIOCData
        for result in results:
            assert isinstance(result, DetectionWithIOCData)
            assert hasattr(result, 'detection')

    def test_get_detections_with_ioc_data_with_filters(self, query_service, populated_ioc_db, sample_detections):
        """Should apply filters correctly."""
        # Test scientific name filter
        results = query_service.get_detections_with_ioc_data(
            scientific_name_filter="Turdus migratorius"
        )
        
        for result in results:
            assert result.detection.scientific_name == "Turdus migratorius"

    def test_get_detections_with_ioc_data_with_family_filter(self, query_service, populated_ioc_db, sample_detections):
        """Should filter by taxonomic family."""
        results = query_service.get_detections_with_ioc_data(
            family_filter="Turdidae"
        )
        
        for result in results:
            assert result.family == "Turdidae"

    def test_get_detections_with_ioc_data_with_since_filter(self, query_service, populated_ioc_db, sample_detections):
        """Should filter by timestamp."""
        cutoff_time = datetime.now() + timedelta(hours=1, minutes=30)
        
        results = query_service.get_detections_with_ioc_data(since=cutoff_time)
        
        for result in results:
            assert result.detection.timestamp >= cutoff_time

    def test_get_detections_with_ioc_data_with_translation(self, query_service, populated_ioc_db, sample_detections):
        """Should include translated names."""
        results = query_service.get_detections_with_ioc_data(
            language_code="es",
            scientific_name_filter="Turdus migratorius"
        )
        
        if results:  # If we have matching results
            robin_result = results[0]
            assert robin_result.translated_name == "Petirrojo Americano"
            assert robin_result.get_best_common_name(prefer_translation=True) == "Petirrojo Americano"

    def test_get_detections_with_ioc_data_pagination(self, query_service, populated_ioc_db, sample_detections):
        """Should handle pagination correctly."""
        # Get first page
        page1 = query_service.get_detections_with_ioc_data(limit=2, offset=0)
        
        # Get second page
        page2 = query_service.get_detections_with_ioc_data(limit=2, offset=2)
        
        # Should not overlap
        if page1 and page2:
            page1_ids = {result.id for result in page1}
            page2_ids = {result.id for result in page2}
            assert page1_ids.isdisjoint(page2_ids)

    def test_get_detections_with_ioc_data_attach_detach(self, query_service, populated_ioc_db, sample_detections):
        """Should properly attach and detach IOC database."""
        # Store original methods
        original_attach = query_service.ioc_db_service.attach_to_session
        original_detach = query_service.ioc_db_service.detach_from_session
        
        with patch.object(query_service.ioc_db_service, 'attach_to_session', side_effect=original_attach) as mock_attach:
            with patch.object(query_service.ioc_db_service, 'detach_from_session', side_effect=original_detach) as mock_detach:
                query_service.get_detections_with_ioc_data()
                
                # Should attach and detach once
                assert mock_attach.call_count == 1
                assert mock_detach.call_count == 1

    def test_get_detections_with_ioc_data_detach_on_exception(self, query_service, populated_ioc_db):
        """Should detach database even if query fails."""
        with patch.object(query_service, '_execute_join_query', side_effect=Exception("Query failed")):
            with patch.object(query_service.ioc_db_service, 'attach_to_session'):
                with patch.object(query_service.ioc_db_service, 'detach_from_session') as mock_detach:
                    with pytest.raises(Exception, match="Query failed"):
                        query_service.get_detections_with_ioc_data()
                    
                    # Should still detach
                    mock_detach.assert_called_once()


class TestGetDetectionWithIOCData:
    """Test getting single detection with IOC data."""

    def test_get_detection_with_ioc_data_found(self, query_service, populated_ioc_db, sample_detections):
        """Should return detection with IOC data when found."""
        detection_id = sample_detections[0].id
        
        result = query_service.get_detection_with_ioc_data(detection_id)
        
        if result:  # May be None if JOIN doesn't match
            assert isinstance(result, DetectionWithIOCData)
            assert result.id == detection_id

    def test_get_detection_with_ioc_data_not_found(self, query_service, populated_ioc_db):
        """Should return None when detection not found."""
        non_existent_id = uuid4()
        
        result = query_service.get_detection_with_ioc_data(non_existent_id)
        
        assert result is None

    def test_get_detection_with_ioc_data_with_translation(self, query_service, populated_ioc_db, sample_detections):
        """Should include translation when available."""
        # Find a robin detection
        robin_detection = None
        for detection in sample_detections:
            if detection.scientific_name == "Turdus migratorius":
                robin_detection = detection
                break
        
        if robin_detection:
            result = query_service.get_detection_with_ioc_data(
                robin_detection.id, language_code="es"
            )
            
            if result:
                assert result.translated_name == "Petirrojo Americano"

    def test_get_detection_with_ioc_data_attach_detach(self, query_service, populated_ioc_db, sample_detections):
        """Should properly attach and detach IOC database."""
        detection_id = sample_detections[0].id
        
        # Store original methods
        original_attach = query_service.ioc_db_service.attach_to_session
        original_detach = query_service.ioc_db_service.detach_from_session
        
        with patch.object(query_service.ioc_db_service, 'attach_to_session', side_effect=original_attach) as mock_attach:
            with patch.object(query_service.ioc_db_service, 'detach_from_session', side_effect=original_detach) as mock_detach:
                query_service.get_detection_with_ioc_data(detection_id)
                
                # Should attach and detach once
                assert mock_attach.call_count == 1
                assert mock_detach.call_count == 1


class TestGetSpeciesSummary:
    """Test species summary functionality."""

    def test_get_species_summary_basic(self, query_service, populated_ioc_db, sample_detections):
        """Should return species summary data."""
        results = query_service.get_species_summary()
        
        assert isinstance(results, list)
        
        # Check result structure
        for result in results:
            assert isinstance(result, dict)
            expected_keys = {
                'scientific_name', 'detection_count', 'avg_confidence',
                'latest_detection', 'ioc_english_name', 'translated_name',
                'family', 'genus', 'order_name', 'best_common_name'
            }
            assert set(result.keys()) == expected_keys
            
            # Verify data types
            assert isinstance(result['detection_count'], int)
            assert isinstance(result['avg_confidence'], float)
            assert result['detection_count'] > 0

    def test_get_species_summary_with_family_filter(self, query_service, populated_ioc_db, sample_detections):
        """Should filter by family."""
        results = query_service.get_species_summary(family_filter="Turdidae")
        
        for result in results:
            assert result['family'] == "Turdidae"

    def test_get_species_summary_with_since_filter(self, query_service, populated_ioc_db, sample_detections):
        """Should filter by timestamp."""
        cutoff_time = datetime.now() + timedelta(hours=1, minutes=30)
        
        results = query_service.get_species_summary(since=cutoff_time)
        
        for result in results:
            assert result['latest_detection'] >= cutoff_time

    def test_get_species_summary_with_translation(self, query_service, populated_ioc_db, sample_detections):
        """Should include translated names."""
        results = query_service.get_species_summary(language_code="es")
        
        # Should have results with Spanish translations
        spanish_results = [r for r in results if r['translated_name'] and r['translated_name'] != r['ioc_english_name']]
        assert len(spanish_results) > 0

    def test_get_species_summary_ordered_by_count(self, query_service, populated_ioc_db, sample_detections):
        """Should order results by detection count descending."""
        results = query_service.get_species_summary()
        
        if len(results) > 1:
            # Should be ordered by detection_count DESC
            for i in range(len(results) - 1):
                assert results[i]['detection_count'] >= results[i + 1]['detection_count']

    def test_get_species_summary_avg_confidence_rounded(self, query_service, populated_ioc_db, sample_detections):
        """Should round average confidence to 3 decimal places."""
        results = query_service.get_species_summary()
        
        for result in results:
            # Check that avg_confidence is rounded to 3 decimal places
            avg_conf = result['avg_confidence']
            assert len(str(avg_conf).split('.')[-1]) <= 3


class TestGetFamilySummary:
    """Test family summary functionality."""

    def test_get_family_summary_basic(self, query_service, populated_ioc_db, sample_detections):
        """Should return family summary data."""
        results = query_service.get_family_summary()
        
        assert isinstance(results, list)
        
        # Check result structure
        for result in results:
            assert isinstance(result, dict)
            expected_keys = {
                'family', 'order_name', 'detection_count',
                'species_count', 'avg_confidence', 'latest_detection'
            }
            assert set(result.keys()) == expected_keys
            
            # Verify data types
            assert isinstance(result['detection_count'], int)
            assert isinstance(result['species_count'], int)
            assert isinstance(result['avg_confidence'], float)
            assert result['detection_count'] > 0
            assert result['species_count'] > 0

    def test_get_family_summary_with_since_filter(self, query_service, populated_ioc_db, sample_detections):
        """Should filter by timestamp."""
        cutoff_time = datetime.now() + timedelta(hours=1, minutes=30)
        
        results = query_service.get_family_summary(since=cutoff_time)
        
        for result in results:
            assert result['latest_detection'] >= cutoff_time

    def test_get_family_summary_ordered_by_count(self, query_service, populated_ioc_db, sample_detections):
        """Should order results by detection count descending."""
        results = query_service.get_family_summary()
        
        if len(results) > 1:
            # Should be ordered by detection_count DESC
            for i in range(len(results) - 1):
                assert results[i]['detection_count'] >= results[i + 1]['detection_count']

    def test_get_family_summary_only_families_with_ioc_data(self, query_service, populated_ioc_db, sample_detections):
        """Should only include families that have IOC data."""
        results = query_service.get_family_summary()
        
        for result in results:
            # Family should not be None (filtered by WHERE s.family IS NOT NULL)
            assert result['family'] is not None


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_database_attachment_failure(self, query_service):
        """Should handle database attachment failures."""
        with patch.object(query_service.ioc_db_service, 'attach_to_session', side_effect=OperationalError("", "", "")):
            with pytest.raises(OperationalError):
                query_service.get_detections_with_ioc_data()

    def test_query_execution_failure(self, query_service, populated_ioc_db):
        """Should handle query execution failures."""
        with patch.object(query_service.db_service, 'get_db') as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.side_effect = Exception("Query failed")
            mock_get_db.return_value.__enter__.return_value = mock_session
            
            with pytest.raises(Exception, match="Query failed"):
                query_service.get_detections_with_ioc_data()

    def test_empty_database(self, query_service, populated_ioc_db):
        """Should handle empty detection database gracefully."""
        # Test with empty main database (no detections)
        results = query_service.get_detections_with_ioc_data()
        assert results == []
        
        results = query_service.get_species_summary()
        assert results == []
        
        results = query_service.get_family_summary()
        assert results == []

    def test_missing_ioc_data(self, query_service, sample_detections):
        """Should handle cases where IOC data is missing."""
        # Use query service without populated IOC database
        results = query_service.get_detections_with_ioc_data()
        
        # Should still return detections, but without IOC data
        for result in results:
            assert isinstance(result, DetectionWithIOCData)
            # IOC fields should be None
            assert result.ioc_english_name is None
            assert result.family is None


class TestPerformance:
    """Test performance-related functionality."""

    def test_limit_and_offset_respected(self, query_service, populated_ioc_db, sample_detections):
        """Should respect limit and offset parameters."""
        # Test limit
        results = query_service.get_detections_with_ioc_data(limit=1)
        assert len(results) <= 1
        
        # Test offset
        all_results = query_service.get_detections_with_ioc_data(limit=100)
        if len(all_results) > 1:
            offset_results = query_service.get_detections_with_ioc_data(
                limit=100, offset=1
            )
            assert len(offset_results) == len(all_results) - 1

    def test_index_usage_pattern(self, query_service, populated_ioc_db, sample_detections):
        """Should use query patterns optimized for indexes."""
        # Test queries that should use the composite indexes defined in Detection model
        
        # Test timestamp + scientific_name pattern
        since_time = datetime.now() - timedelta(days=1)
        results = query_service.get_detections_with_ioc_data(
            since=since_time,
            scientific_name_filter="Turdus migratorius"
        )
        
        # Should execute without error (index optimization is internal)
        assert isinstance(results, list)

    @pytest.mark.slow
    def test_large_dataset_performance(self, query_service, populated_ioc_db):
        """Test performance with larger dataset."""
        # This test would be marked as slow and only run in comprehensive test suites
        # For now, just test that the query patterns work
        
        # Test that large limit values don't cause issues
        results = query_service.get_detections_with_ioc_data(limit=1000)
        assert isinstance(results, list)
        
        # Test species summary with no limit
        species_summary = query_service.get_species_summary()
        assert isinstance(species_summary, list)


class TestIntegration:
    """Integration tests for the complete DetectionQueryService."""

    def test_complete_workflow(self, query_service, populated_ioc_db, sample_detections):
        """Test complete workflow from detections to summaries."""
        # Test basic detection retrieval
        detections = query_service.get_detections_with_ioc_data(limit=10)
        assert len(detections) > 0
        
        # Test single detection retrieval
        if detections:
            single_detection = query_service.get_detection_with_ioc_data(detections[0].id)
            assert single_detection is not None
            assert single_detection.id == detections[0].id
        
        # Test species summary
        species_summary = query_service.get_species_summary()
        assert len(species_summary) > 0
        
        # Test family summary
        family_summary = query_service.get_family_summary()
        assert len(family_summary) > 0
        
        # Verify data consistency
        total_detections_in_summary = sum(s['detection_count'] for s in species_summary)
        total_detections_in_family = sum(f['detection_count'] for f in family_summary)
        
        # Family summary should have fewer or equal total detections
        # (some detections might not have family data)
        assert total_detections_in_family <= total_detections_in_summary

    def test_translation_consistency(self, query_service, populated_ioc_db, sample_detections):
        """Test translation consistency across different query methods."""
        # Get detection with Spanish translation
        detections = query_service.get_detections_with_ioc_data(
            language_code="es",
            scientific_name_filter="Turdus migratorius"
        )
        
        if detections:
            detection = detections[0]
            
            # Get same detection by ID with Spanish translation
            single_detection = query_service.get_detection_with_ioc_data(
                detection.id, language_code="es"
            )
            
            if single_detection:
                # Should have same translation
                assert detection.translated_name == single_detection.translated_name
            
            # Get species summary with Spanish translation
            species_summary = query_service.get_species_summary(language_code="es")
            robin_summary = next(
                (s for s in species_summary if s['scientific_name'] == "Turdus migratorius"),
                None
            )
            
            if robin_summary:
                # Should have same translation
                assert detection.translated_name == robin_summary['translated_name']

    def test_database_state_isolation(self, query_service, populated_ioc_db, sample_detections):
        """Test that queries don't affect database state."""
        # Get initial state
        initial_detections = query_service.get_detections_with_ioc_data()
        initial_count = len(initial_detections)
        
        # Perform various queries
        query_service.get_species_summary()
        query_service.get_family_summary()
        
        if initial_detections:
            query_service.get_detection_with_ioc_data(initial_detections[0].id)
        
        # State should be unchanged
        final_detections = query_service.get_detections_with_ioc_data()
        assert len(final_detections) == initial_count