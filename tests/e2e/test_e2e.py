import subprocess
import time

import httpx
import pytest


@pytest.mark.expensive
def test_root_endpoint_e2e(docker_compose_up_down) -> None:
    """Test the root endpoint of the BirdNET-Pi application."""
    response = httpx.get("http://localhost:8000")
    assert response.status_code == 200
    assert "BirdNET-Pi" in response.text


@pytest.mark.expensive
def test_sqladmin_detection_list_e2e(docker_compose_up_down) -> None:
    """Test the SQLAdmin Detection list endpoint."""
    # Generate dummy data first to ensure the database has detection records
    subprocess.run(
        ["docker", "exec", "birdnet-pi", "/opt/birdnetpi/.venv/bin/generate-dummy-data"],
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
