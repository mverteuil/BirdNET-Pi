import os
import subprocess
import time
from collections.abc import Generator
from typing import Any

import httpx
import pytest


@pytest.fixture(scope="module")
def docker_compose_up_down() -> Generator[None, None, None]:
    """Bring up and tear down Docker Compose services for e2e tests.

    Uses docker-compose.test.yml which separates static assets (models, language DBs)
    from runtime data. This allows us to preserve expensive downloads between test runs
    while still cleaning the test database.
    """
    env = os.environ.copy()

    # Use the test-specific compose file
    compose_cmd = ["docker", "compose", "-f", "docker-compose.test.yml"]

    # Bring up Docker Compose and wait for services to be healthy
    subprocess.run([*compose_cmd, "up", "-d", "--build", "--wait"], check=True, env=env)
    subprocess.run(["docker", "ps"], check=True)
    subprocess.run(["docker", "logs", "birdnet-pi-test"], check=True)
    yield

    # Bring down Docker Compose but keep the volume to preserve models
    subprocess.run([*compose_cmd, "down"], check=True, env=env)

    # Clean only the runtime database file, preserving expensive assets
    # This allows tests to start fresh while avoiding re-downloading models
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                "birdnet-pi_birdnet-test-data:/data",
                "alpine",
                "rm",
                "-f",
                "/data/database/birdnetpi.db",
            ],
            check=False,  # Don't fail if file doesn't exist
        )
    except Exception:
        pass  # It's OK if this fails (e.g., volume doesn't exist yet)


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
        ["docker", "exec", "birdnet-pi-test", "/opt/birdnetpi/.venv/bin/generate-dummy-data"],
        check=True,
    )

    # Wait for the FastAPI service to be fully ready after restart
    # Retry the basic endpoint first to ensure the service is up
    for _attempt in range(10):
        try:
            health_check = httpx.get("http://localhost:8000/", timeout=3)
            if health_check.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        pytest.fail("FastAPI service did not become ready after dummy data generation")

    response = httpx.get("http://localhost:8000/admin/database/detection/list")
    assert response.status_code == 200
    assert "Detections" in response.text

    assert "id" in response.text
    assert "scientific_name" in response.text or "common_name" in response.text
    assert "confidence" in response.text
    assert "timestamp" in response.text
