"""Tests for SQLAdmin configuration and setup."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from birdnetpi.web.routers.sqladmin_view_routes import (
    AudioFileAdmin,
    DetectionAdmin,
    setup_sqladmin,
)


class TestSQLAdminViewRoutes:
    """Test SQLAdmin configuration and model views."""

    def test_detection_admin_model_configuration(self):
        """Test DetectionAdmin model view configuration."""
        # Verify the model view is properly configured
        assert hasattr(DetectionAdmin, 'column_list')
        assert DetectionAdmin.column_list is not None
        
        # Check that expected columns are configured
        column_names = [col.name for col in DetectionAdmin.column_list]
        expected_columns = ['id', 'scientific_name', 'common_name_ioc', 'confidence', 'timestamp']
        
        for expected_col in expected_columns:
            assert expected_col in column_names

    def test_audio_file_admin_model_configuration(self):
        """Test AudioFileAdmin model view configuration."""
        # Verify the model view is properly configured
        assert hasattr(AudioFileAdmin, 'column_list')
        assert AudioFileAdmin.column_list is not None
        
        # Check that expected columns are configured
        column_names = [col.name for col in AudioFileAdmin.column_list]
        expected_columns = ['id', 'file_path', 'duration', 'recording_start_time']
        
        for expected_col in expected_columns:
            assert expected_col in column_names

    @patch('birdnetpi.web.routers.sqladmin_view_routes.Admin')
    def test_setup_sqladmin_creates_admin_instance(self, mock_admin_class):
        """Test that setup_sqladmin creates and configures Admin instance."""
        # Create mock FastAPI app with DI container
        app = FastAPI()
        mock_container = MagicMock()
        mock_db_service = MagicMock()
        mock_engine = MagicMock()
        mock_db_service.engine = mock_engine
        mock_container.database_service.return_value = mock_db_service
        app.container = mock_container
        
        # Create mock Admin instance
        mock_admin_instance = MagicMock()
        mock_admin_class.return_value = mock_admin_instance
        
        # Call setup function
        result = setup_sqladmin(app)
        
        # Verify Admin was instantiated with correct parameters
        mock_admin_class.assert_called_once_with(app, mock_engine,
                                                 base_url="/admin/database")
        
        # Verify model views were added
        assert mock_admin_instance.add_view.call_count == 2
        
        # Verify the correct model views were added
        call_args = [call.args[0] for call in mock_admin_instance.add_view.call_args_list]
        assert DetectionAdmin in call_args
        assert AudioFileAdmin in call_args
        
        # Verify return value
        assert result == mock_admin_instance

    @patch('birdnetpi.web.routers.sqladmin_view_routes.Admin')
    def test_setup_sqladmin_returns_admin_instance(self, mock_admin_class):
        """Test that setup_sqladmin returns the Admin instance."""
        app = FastAPI()
        mock_container = MagicMock()
        mock_db_service = MagicMock()
        mock_engine = MagicMock()
        mock_db_service.engine = mock_engine
        mock_container.database_service.return_value = mock_db_service
        app.container = mock_container
        
        mock_admin_instance = MagicMock()
        mock_admin_class.return_value = mock_admin_instance
        
        result = setup_sqladmin(app)
        
        assert result is mock_admin_instance

    def test_detection_admin_inherits_from_model_view(self):
        """Test that DetectionAdmin properly inherits from ModelView."""
        # Check that DetectionAdmin has the expected base classes
        base_class_names = [cls.__name__ for cls in DetectionAdmin.__mro__]
        assert 'ModelView' in base_class_names

    def test_audio_file_admin_inherits_from_model_view(self):
        """Test that AudioFileAdmin properly inherits from ModelView."""
        # Check that AudioFileAdmin has the expected base classes
        base_class_names = [cls.__name__ for cls in AudioFileAdmin.__mro__]
        assert 'ModelView' in base_class_names