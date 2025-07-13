import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="module")
def docker_compose_up_down():
    # Bring up Docker Compose
    subprocess.run(["docker", "compose", "up", "-d", "--build"], check=True)
    # Wait for services to be ready
    time.sleep(10)  # Adjust as needed
    yield
    # Bring down Docker Compose
    subprocess.run(["docker", "compose", "down"], check=True)


def test_root_endpoint_e2e(docker_compose_up_down):
    response = httpx.get("http://localhost:80")
    assert response.status_code == 200
    assert "BirdNET-Pi" in response.text
