"""Tests for admin API routes."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.utils.path_resolver import PathResolver
from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.admin_api_routes import router


@pytest.fixture
def client(tmp_path):
    """Create test client with admin API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Override the path_resolver with a mock
    mock_path_resolver = MagicMock(spec=PathResolver)
    # Set return values to prevent MagicMock folder creation using tmp_path (as Path objects)
    mock_path_resolver.get_ioc_database_path.return_value = tmp_path / "ioc_reference.db"
    mock_path_resolver.get_models_dir.return_value = tmp_path / "models"
    mock_path_resolver.get_avibase_database_path.return_value = tmp_path / "avibase.db"
    mock_path_resolver.get_patlevin_database_path.return_value = tmp_path / "patlevin.db"
    container.path_resolver.override(mock_path_resolver)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.admin_api_routes"])
    app.container = container  # type: ignore[attr-defined]

    # Include the router with the same prefix as in factory
    app.include_router(router, prefix="/admin/config")

    # Create and return test client
    client = TestClient(app)

    # Store the mock for access in tests
    client.mock_path_resolver = mock_path_resolver  # type: ignore[attr-defined]

    return client


class TestAdminAPIRoutes:
    """Test class for admin API endpoints."""

    def test_validate_yaml_config_valid(self, client, tmp_path):
        """Test YAML config validation with valid YAML."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site\nlatitude: 40.0\nlongitude: -74.0")

        # Mock the file resolver method (returns Path object)
        client.mock_path_resolver.get_birdnetpi_config_path.return_value = config_file

        valid_yaml = """
site_name: "Test BirdNET-Pi"
latitude: 40.7128
longitude: -74.0060
species_confidence_threshold: 0.03
        """

        response = client.post("/admin/config/validate", json={"yaml_content": valid_yaml})

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "message" in data

    def test_validate_yaml_config_invalid(self, client, tmp_path):
        """Test YAML config validation with invalid YAML."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site")

        # Mock the file resolver method (returns Path object)
        client.mock_path_resolver.get_birdnetpi_config_path.return_value = config_file

        invalid_yaml = """
site_name: "Test BirdNET-Pi"
invalid_yaml: [unclosed bracket
        """

        response = client.post("/admin/config/validate", json={"yaml_content": invalid_yaml})

        assert response.status_code == 200  # The endpoint returns 200 with error in body
        data = response.json()
        assert data["valid"] is False
        assert "error" in data

    def test_save_yaml_config(self, client, tmp_path):
        """Test saving YAML config successfully."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Old Site")

        # Mock the file resolver method (returns Path object)
        client.mock_path_resolver.get_birdnetpi_config_path.return_value = config_file

        new_yaml = """
site_name: "New Test Site"
latitude: 41.0
longitude: -75.0
species_confidence_threshold: 0.05
        """

        response = client.post("/admin/config/save", json={"yaml_content": new_yaml})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_save_yaml_config_invalid(self, client, tmp_path):
        """Test saving invalid YAML config."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site")

        # Mock the file resolver method (returns Path object)
        client.mock_path_resolver.get_birdnetpi_config_path.return_value = config_file

        invalid_yaml = """
site_name: "Test BirdNET-Pi"
invalid_yaml: [unclosed bracket
        """

        response = client.post("/admin/config/save", json={"yaml_content": invalid_yaml})

        assert response.status_code == 200  # The endpoint returns 200 with error in body
        data = response.json()
        assert data["success"] is False
        assert "error" in data
