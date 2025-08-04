import subprocess
from collections.abc import Generator
from typing import Any

import httpx
import pytest


@pytest.fixture(scope="module")
def docker_compose_up_down() -> Generator[None, None, None]:
    """Bring up and tear down Docker Compose services for e2e tests."""
    # Bring up Docker Compose
    # Bring up Docker Compose and wait for services to be healthy
    subprocess.run(["docker", "compose", "up", "-d", "--build", "--wait"], check=True)
    subprocess.run(["docker", "ps"], check=True)
    subprocess.run(["docker", "logs", "birdnet-pi"], check=True)
    yield
    # Bring down Docker Compose
    subprocess.run(["docker", "compose", "down"], check=True)


@pytest.mark.expensive
def test_root_endpoint_e2e(docker_compose_up_down: Any) -> None:
    """Test the root endpoint of the BirdNET-Pi application."""
    response = httpx.get("http://localhost:8000")
    assert response.status_code == 200
    assert "BirdNET-Pi" in response.text


@pytest.mark.expensive
def test_sqladmin_detection_list_e2e(docker_compose_up_down: Any) -> None:
    """Test the SQLAdmin Detection list endpoint."""
    # Generate dummy data first to ensure the database has detection records
    subprocess.run(
        ["docker", "exec", "birdnet-pi", "/opt/birdnetpi/.venv/bin/generate-dummy-data"], check=True
    )

    response = httpx.get("http://localhost:8000/admin/detection/list")
    assert response.status_code == 200
    assert "Detections" in response.text

    assert "id" in response.text
    assert "scientific_name" in response.text or "common_name_ioc" in response.text
    assert "confidence" in response.text
    assert "timestamp" in response.text
