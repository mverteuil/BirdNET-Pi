"""Tests for database models."""

import uuid
from unittest.mock import MagicMock

import pytest

from birdnetpi.models.database_models import GUID, Detection


class TestGUIDTypeDecorator:
    """Test the GUID TypeDecorator class."""

    def test_process_bind_param_with_none(self):
        """Test process_bind_param returns None when value is None."""
        guid = GUID()
        dialect = MagicMock()
        
        result = guid.process_bind_param(None, dialect)
        
        assert result is None  # This covers line 26

    def test_process_bind_param_with_uuid_instance(self):
        """Test process_bind_param returns string when value is UUID instance."""
        guid = GUID()
        dialect = MagicMock()
        test_uuid = uuid.uuid4()
        
        result = guid.process_bind_param(test_uuid, dialect)
        
        assert result == str(test_uuid)

    def test_process_bind_param_with_string_uuid(self):
        """Test process_bind_param converts string to UUID then string."""
        guid = GUID()
        dialect = MagicMock()
        test_uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        
        result = guid.process_bind_param(test_uuid_str, dialect)
        
        # This covers line 28 - converting string to UUID then back to string
        assert result == test_uuid_str

    def test_process_result_value_with_none(self):
        """Test process_result_value returns None when value is None."""
        guid = GUID()
        dialect = MagicMock()
        
        result = guid.process_result_value(None, dialect)
        
        assert result is None  # This covers line 34

    def test_process_result_value_with_uuid_instance(self):
        """Test process_result_value returns UUID when value is already UUID."""
        guid = GUID()
        dialect = MagicMock()
        test_uuid = uuid.uuid4()
        
        result = guid.process_result_value(test_uuid, dialect)
        
        assert result == test_uuid  # This covers line 37

    def test_process_result_value_with_string(self):
        """Test process_result_value converts string to UUID."""
        guid = GUID()
        dialect = MagicMock()
        test_uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        expected_uuid = uuid.UUID(test_uuid_str)
        
        result = guid.process_result_value(test_uuid_str, dialect)
        
        assert result == expected_uuid
        assert isinstance(result, uuid.UUID)

    def test_load_dialect_impl(self):
        """Test load_dialect_impl returns CHAR(36) type descriptor."""
        guid = GUID()
        dialect = MagicMock()
        
        result = guid.load_dialect_impl(dialect)
        
        dialect.type_descriptor.assert_called_once()
        assert result == dialect.type_descriptor.return_value

    def test_cache_ok_is_true(self):
        """Test that cache_ok is set to True."""
        guid = GUID()
        assert guid.cache_ok is True


class TestDetection:
    """Test the Detection model class."""

    def test_get_display_name_prefers_ioc_name(self):
        """Test get_display_name returns IOC name when available."""
        detection = Detection()
        detection.common_name_ioc = "American Robin"
        detection.common_name_tensor = "American Robin Tensor"
        detection.scientific_name = "Turdus migratorius"
        
        result = detection.get_display_name()
        
        assert result == "American Robin"

    def test_get_display_name_falls_back_to_tensor_name(self):
        """Test get_display_name returns tensor name when IOC name is None."""
        detection = Detection()
        detection.common_name_ioc = None
        detection.common_name_tensor = "American Robin Tensor"
        detection.scientific_name = "Turdus migratorius"
        
        result = detection.get_display_name()
        
        assert result == "American Robin Tensor"

    def test_get_display_name_falls_back_to_scientific_name(self):
        """Test get_display_name returns scientific name when both common names are None."""
        detection = Detection()
        detection.common_name_ioc = None
        detection.common_name_tensor = None
        detection.scientific_name = "Turdus migratorius"
        
        result = detection.get_display_name()
        
        assert result == "Turdus migratorius"