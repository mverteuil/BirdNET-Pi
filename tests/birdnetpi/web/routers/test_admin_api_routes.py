"""Tests for admin API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birdnetpi.web.core.container import Container
from birdnetpi.web.routers.admin_api_routes import router


@pytest.fixture
def client(tmp_path, path_resolver):
    """Create test client with admin API routes and mocked dependencies."""
    # Create the app
    app = FastAPI()

    # Create the real container
    container = Container()

    # Use the global path_resolver fixture and customize it
    path_resolver.get_ioc_database_path = lambda: tmp_path / "ioc_reference.db"
    path_resolver.get_models_dir = lambda: tmp_path / "models"
    path_resolver.get_avibase_database_path = lambda: tmp_path / "avibase.db"
    path_resolver.get_patlevin_database_path = lambda: tmp_path / "patlevin.db"
    container.path_resolver.override(path_resolver)

    # Wire the container
    container.wire(modules=["birdnetpi.web.routers.admin_api_routes"])
    app.container = container  # type: ignore[attr-defined]

    # Include the router with the same prefix as in factory
    app.include_router(router, prefix="/admin/config")

    # Create and return test client
    client = TestClient(app)

    # Store the path resolver for access in tests
    client.mock_path_resolver = path_resolver  # type: ignore[attr-defined]

    return client


class TestAdminAPIRoutes:
    """Test class for admin API endpoints."""

    def test_validate_yaml_config_valid(self, client, tmp_path):
        """Test YAML config validation with valid YAML."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("site_name: Test Site\nlatitude: 40.0\nlongitude: -74.0")

        # Mock the file resolver method (returns Path object)
        client.mock_path_resolver.get_birdnetpi_config_path = lambda: config_file

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
        client.mock_path_resolver.get_birdnetpi_config_path = lambda: config_file

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
        client.mock_path_resolver.get_birdnetpi_config_path = lambda: config_file

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
        client.mock_path_resolver.get_birdnetpi_config_path = lambda: config_file

        invalid_yaml = """
site_name: "Test BirdNET-Pi"
invalid_yaml: [unclosed bracket
        """

        response = client.post("/admin/config/save", json={"yaml_content": invalid_yaml})

        assert response.status_code == 200  # The endpoint returns 200 with error in body
        data = response.json()
        assert data["success"] is False
        assert "error" in data
