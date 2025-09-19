"""Tests for SQLAdmin configuration and setup."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI

from birdnetpi.web.routers.sqladmin_view_routes import (
    AudioFileAdmin,
    DetectionAdmin,
    WeatherAdmin,
    setup_sqladmin,
)


class TestSQLAdminViewRoutes:
    """Test SQLAdmin configuration and model views."""

    def test_detection_admin_model_configuration(self):
        """Should detectionAdmin model view configuration."""
        # Verify the model view is properly configured
        assert hasattr(DetectionAdmin, "column_list")
        assert DetectionAdmin.column_list is not None

        # Check that expected columns are configured
        column_names = DetectionAdmin.column_list  # Already strings
        expected_columns = ["id", "scientific_name", "common_name", "confidence", "timestamp"]

        for expected_col in expected_columns:
            assert expected_col in column_names

    def test_audio_file_admin_model_configuration(self):
        """Should audioFileAdmin model view configuration."""
        # Verify the model view is properly configured
        assert hasattr(AudioFileAdmin, "column_list")
        assert AudioFileAdmin.column_list is not None

        # Check that expected columns are configured
        column_names = AudioFileAdmin.column_list  # Already strings
        expected_columns = ["id", "file_path", "duration"]

        for expected_col in expected_columns:
            assert expected_col in column_names

    def test_weather_admin_model_configuration(self):
        """Should weatherAdmin model view configuration."""
        # Verify the model view is properly configured
        assert hasattr(WeatherAdmin, "column_list")
        assert WeatherAdmin.column_list is not None

        # Check that expected columns are configured
        column_names = WeatherAdmin.column_list  # Already strings
        expected_columns = [
            "timestamp",
            "latitude",
            "longitude",
            "temperature",
            "humidity",
            "wind_speed",
        ]

        for expected_col in expected_columns:
            assert expected_col in column_names

    @patch("birdnetpi.web.routers.sqladmin_view_routes.Container")
    @patch("birdnetpi.web.routers.sqladmin_view_routes.Admin")
    def test_setup_sqladmin_creates_admin_instance(self, mock_admin_class, mock_container_class):
        """Should setup_sqladmin creates and configures Admin instance."""
        # Create mock FastAPI app
        app = FastAPI()

        # Set up mock container instance
        mock_container = MagicMock()
        mock_db_service = MagicMock()
        mock_async_engine = AsyncMock()
        mock_db_service.async_engine = mock_async_engine
        mock_container.core_database.return_value = mock_db_service
        mock_container_class.return_value = mock_container

        # Create mock Admin instance
        mock_admin_instance = MagicMock()
        mock_admin_class.return_value = mock_admin_instance

        # Call setup function
        result = setup_sqladmin(app)

        # Verify Admin was instantiated with correct parameters
        mock_admin_class.assert_called_once_with(
            app, mock_async_engine, base_url="/admin/database", title="BirdNET-Pi Database Admin"
        )

        # Verify model views were added
        assert mock_admin_instance.add_view.call_count == 3

        # Verify the correct model views were added
        call_args = [call.args[0] for call in mock_admin_instance.add_view.call_args_list]
        assert DetectionAdmin in call_args
        assert AudioFileAdmin in call_args
        assert WeatherAdmin in call_args

        # Verify return value
        assert result == mock_admin_instance

    @patch("birdnetpi.web.routers.sqladmin_view_routes.Container")
    @patch("birdnetpi.web.routers.sqladmin_view_routes.Admin")
    def test_setup_sqladmin_returns_admin_instance(self, mock_admin_class, mock_container_class):
        """Should setup_sqladmin returns the Admin instance."""
        app = FastAPI()

        # Set up mock container instance
        mock_container = MagicMock()
        mock_db_service = MagicMock()
        mock_async_engine = AsyncMock()
        mock_db_service.async_engine = mock_async_engine
        mock_container.core_database.return_value = mock_db_service
        mock_container_class.return_value = mock_container

        mock_admin_instance = MagicMock()
        mock_admin_class.return_value = mock_admin_instance

        result = setup_sqladmin(app)

        assert result is mock_admin_instance

    def test_detection_admin_inherits_from_model_view(self):
        """Should detectionAdmin properly inherits from ModelView."""
        # Check that DetectionAdmin has the expected base classes
        base_class_names = [cls.__name__ for cls in DetectionAdmin.__mro__]
        assert "ModelView" in base_class_names

    def test_audio_file_admin_inherits_from_model_view(self):
        """Should audioFileAdmin properly inherits from ModelView."""
        # Check that AudioFileAdmin has the expected base classes
        base_class_names = [cls.__name__ for cls in AudioFileAdmin.__mro__]
        assert "ModelView" in base_class_names

    def test_weather_admin_inherits_from_model_view(self):
        """Should weatherAdmin properly inherits from ModelView."""
        # Check that WeatherAdmin has the expected base classes
        base_class_names = [cls.__name__ for cls in WeatherAdmin.__mro__]
        assert "ModelView" in base_class_names
