"""Tests for SQLAdmin configuration and setup."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.ext.asyncio import AsyncEngine

from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.web.core.container import Container
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
        assert hasattr(DetectionAdmin, "column_list")
        assert DetectionAdmin.column_list is not None
        column_names = DetectionAdmin.column_list
        expected_columns = ["id", "scientific_name", "common_name", "confidence", "timestamp"]
        for expected_col in expected_columns:
            assert expected_col in column_names

    def test_audio_file_admin_model_configuration(self):
        """Should audioFileAdmin model view configuration."""
        assert hasattr(AudioFileAdmin, "column_list")
        assert AudioFileAdmin.column_list is not None
        column_names = AudioFileAdmin.column_list
        expected_columns = ["id", "file_path", "duration"]
        for expected_col in expected_columns:
            assert expected_col in column_names

    def test_weather_admin_model_configuration(self):
        """Should weatherAdmin model view configuration."""
        assert hasattr(WeatherAdmin, "column_list")
        assert WeatherAdmin.column_list is not None
        column_names = WeatherAdmin.column_list
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

    @patch("birdnetpi.web.routers.sqladmin_view_routes.Container", autospec=True)
    @patch("birdnetpi.web.routers.sqladmin_view_routes.Admin", autospec=True)
    def test_setup_sqladmin_creates_admin_instance(self, mock_admin_class, mock_container_class):
        """Should setup_sqladmin creates and configures Admin instance."""
        app = FastAPI()
        mock_container = MagicMock(spec=Container)
        # AsyncEngine is not awaited in this context, use MagicMock with proper spec
        mock_async_engine = MagicMock(spec=AsyncEngine)
        mock_db_service = MagicMock(spec=CoreDatabaseService, async_engine=mock_async_engine)
        mock_container.core_database.return_value = mock_db_service
        mock_container_class.return_value = mock_container
        mock_admin_instance = MagicMock(spec=Admin)
        mock_admin_class.return_value = mock_admin_instance
        result = setup_sqladmin(app)
        # Check that Admin was called with the expected parameters
        # Note: authentication_backend is also passed, but we check for the core params
        mock_admin_class.assert_called_once()
        call_args, call_kwargs = mock_admin_class.call_args
        assert call_args[0] == app
        assert call_args[1] == mock_async_engine
        assert call_kwargs["base_url"] == "/admin/database"
        assert call_kwargs["title"] == "BirdNET-Pi Database Admin"
        assert "authentication_backend" in call_kwargs
        assert mock_admin_instance.add_view.call_count == 3
        call_args = [call.args[0] for call in mock_admin_instance.add_view.call_args_list]
        assert DetectionAdmin in call_args
        assert AudioFileAdmin in call_args
        assert WeatherAdmin in call_args
        assert result == mock_admin_instance

    @patch("birdnetpi.web.routers.sqladmin_view_routes.Container", autospec=True)
    @patch("birdnetpi.web.routers.sqladmin_view_routes.Admin", autospec=True)
    def test_setup_sqladmin_returns_admin_instance(self, mock_admin_class, mock_container_class):
        """Should setup_sqladmin returns the Admin instance."""
        app = FastAPI()
        mock_container = MagicMock(spec=Container)
        # AsyncEngine is not awaited in this context, use MagicMock with proper spec
        mock_async_engine = MagicMock(spec=AsyncEngine)
        mock_db_service = MagicMock(spec=CoreDatabaseService, async_engine=mock_async_engine)
        mock_container.core_database.return_value = mock_db_service
        mock_container_class.return_value = mock_container
        mock_admin_instance = MagicMock(spec=Admin)
        mock_admin_class.return_value = mock_admin_instance
        result = setup_sqladmin(app)
        assert result is mock_admin_instance

    def test_detection_admin_inherits_from_model_view(self):
        """Should detectionAdmin properly inherits from ModelView."""
        base_class_names = [cls.__name__ for cls in DetectionAdmin.__mro__]
        assert "ModelView" in base_class_names

    def test_audio_file_admin_inherits_from_model_view(self):
        """Should audioFileAdmin properly inherits from ModelView."""
        base_class_names = [cls.__name__ for cls in AudioFileAdmin.__mro__]
        assert "ModelView" in base_class_names

    def test_weather_admin_inherits_from_model_view(self):
        """Should weatherAdmin properly inherits from ModelView."""
        base_class_names = [cls.__name__ for cls in WeatherAdmin.__mro__]
        assert "ModelView" in base_class_names
