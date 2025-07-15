import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="module")
def docker_compose_up_down() -> None:
    """Bring up and tear down Docker Compose services for e2e tests."""
    # Bring up Docker Compose
    subprocess.run(["docker", "compose", "up", "-d", "--build"], check=True)
    # Wait for services to be ready
    time.sleep(10)  # Adjust as needed
    subprocess.run(["docker", "ps"], check=True)
    subprocess.run(["docker", "logs", "birdnet-pi"], check=True)
    yield
    # Bring down Docker Compose
    subprocess.run(["docker", "compose", "down"], check=True)


@pytest.mark.expensive
def test_root_endpoint_e2e(docker_compose_up_down) -> None:
    """Test the root endpoint of the BirdNET-Pi application."""
    response = httpx.get("http://localhost:80")
    assert response.status_code == 200
    assert "BirdNET-Pi" in response.text
