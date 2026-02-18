import subprocess
import time

import httpx
import pytest


@pytest.mark.expensive
def test_root_endpoint_e2e(docker_compose_up_down, authenticated_e2e_client) -> None:
    """Should serve the root endpoint of the BirdNET-Pi application."""
    # Need authenticated client since root page requires login
    response = authenticated_e2e_client.get("/")
    assert response.status_code == 200
    assert "BirdNET-Pi" in response.text


@pytest.mark.expensive
def test_sqladmin_detection_list_e2e(docker_compose_up_down) -> None:
    """Should display the SQLAdmin Detection list endpoint."""
    # Generate dummy data first to ensure the database has detection records
    # Use capture_output to get error details if it fails
    result = subprocess.run(
        ["docker", "exec", "birdnet-pi", "python", "-m", "birdnetpi.cli.generate_dummy_data"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # If it fails due to missing column, recreate database and retry
        if "no such column: detections.hour_epoch" in result.stderr:
            # Remove old database to force recreation with new schema
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "birdnet-pi",
                    "rm",
                    "-f",
                    "/var/lib/birdnetpi/database/birdnetpi.db",
                ],
                check=True,
            )
            # Restart container to recreate database
            subprocess.run(["docker", "restart", "birdnet-pi"], check=True)
            # Wait for container to be healthy
            time.sleep(5)
            # Retry dummy data generation
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "birdnet-pi",
                    "python",
                    "-m",
                    "birdnetpi.cli.generate_dummy_data",
                ],
                check=True,
            )
        else:
            # Other error, fail with details
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            result.check_returncode()

    # Wait for the FastAPI service to be fully ready after restart
    # Retry the health endpoint first to ensure the service is up
    for _attempt in range(10):
        try:
            health_check = httpx.get("http://localhost:8000/api/health/ready", timeout=3)
            if health_check.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        pytest.fail("FastAPI service did not become ready after dummy data generation")

    # Need authenticated client for SQLAdmin access
    # Note: We need to recreate the client after container restart since session may be lost
    # Re-setup admin and authenticate (container may have been restarted)
    response = httpx.get("http://localhost:8000/", follow_redirects=False)
    if response.status_code == 303 and "/admin/setup" in response.headers.get("location", ""):
        httpx.post(
            "http://localhost:8000/admin/setup",
            data={"username": "admin", "password": "e2e-test-password-123"},
            follow_redirects=False,
        )

    client = httpx.Client(base_url="http://localhost:8000")
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "e2e-test-password-123"},
        follow_redirects=False,
    )
    response = client.get("/admin/database/detection/list")
    client.close()
    assert response.status_code == 200
    assert "Detections" in response.text

    assert "id" in response.text
    assert "scientific_name" in response.text or "common_name" in response.text
    assert "confidence" in response.text
    assert "timestamp" in response.text


@pytest.mark.expensive
def test_profiling_disabled_by_default(docker_compose_up_down, authenticated_e2e_client) -> None:
    """Should not enable profiling when ENABLE_PROFILING is not set.

    This test is in the main e2e file because it needs the regular Docker
    environment without profiling enabled.
    """
    # Request the root page with ?profile=1
    response = authenticated_e2e_client.get("/?profile=1")
    assert response.status_code == 200

    # Should return the normal page, not profiling output
    assert "BirdNET-Pi" in response.text
    assert "pyinstrument" not in response.text.lower()
    # Check for pyinstrument-specific profiling elements
    assert '"identifier"' not in response.text  # pyinstrument JSON output
    assert "cpu utilization" not in response.text.lower()
