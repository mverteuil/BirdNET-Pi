"""Tests for admin API routes."""

from unittest.mock import MagicMock
from pathlib import Path
import tempfile

import pytest
from dependency_injector import containers, providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.utils.file_path_resolver import FilePathResolver
from birdnetpi.web.routers.admin_api_routes import router


class TestContainer(containers.DeclarativeContainer):
    """Test container for dependency injection."""

    file_resolver = providers.Singleton(MagicMock, spec=FilePathResolver)


@pytest.fixture
def app_with_admin_api_routes():
    """Create FastAPI app with admin API router and dependencies."""
    app = FastAPI()
    
    # Create test container
    container = TestContainer()
    
    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.admin_api_routes"])
    app.container = container
    
    app.include_router(router, prefix="/admin/api")
    return app


@pytest.fixture
def client(app_with_admin_api_routes):
    """Create test client with admin API routes."""
    return TestClient(app_with_admin_api_routes)


class TestAdminAPIRoutes:
    """Test class for admin API endpoints."""

    def test_validate_yaml_config_valid(self, client, tmp_path):
        """Test YAML config validation with valid YAML."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site\nlatitude: 40.0\nlongitude: -74.0")
        
        # Mock file resolver
        client.app.container.file_resolver().get_birdnetpi_config_path.return_value = str(config_file)
        
        valid_yaml = """
site_name: "Test BirdNET-Pi"
latitude: 40.7128
longitude: -74.0060
confidence: 0.7
        """
        
        response = client.post(
            "/admin/api/config/validate",
            json={"yaml_content": valid_yaml}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "config" in data

    def test_validate_yaml_config_invalid(self, client, tmp_path):
        """Test YAML config validation with invalid YAML."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site")
        
        # Mock file resolver
        client.app.container.file_resolver().get_birdnetpi_config_path.return_value = str(config_file)
        
        invalid_yaml = """
site_name: "Test BirdNET-Pi"
invalid_yaml: [unclosed bracket
        """
        
        response = client.post(
            "/admin/api/config/validate",
            json={"yaml_content": invalid_yaml}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["valid"] is False
        assert "error" in data

    def test_save_yaml_config_success(self, client, tmp_path):
        """Test saving YAML config successfully."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Old Site")
        
        # Mock file resolver
        client.app.container.file_resolver().get_birdnetpi_config_path.return_value = str(config_file)
        
        new_yaml = """
site_name: "New Test Site"
latitude: 41.0
longitude: -75.0
confidence: 0.8
        """
        
        response = client.post(
            "/admin/api/config/save",
            json={"yaml_content": new_yaml}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_save_yaml_config_invalid(self, client, tmp_path):
        """Test saving invalid YAML config."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site")
        
        # Mock file resolver
        client.app.container.file_resolver().get_birdnetpi_config_path.return_value = str(config_file)
        
        invalid_yaml = """
site_name: "Test BirdNET-Pi"
invalid_yaml: [unclosed bracket
        """
        
        response = client.post(
            "/admin/api/config/save",
            json={"yaml_content": invalid_yaml}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "error" in data