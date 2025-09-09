"""E2E tests for pyinstrument profiling middleware functionality.

All tests in this module share a single Docker container instance using
the profiling container variant (birdnet-pi-profiling) which includes
pyinstrument and has ENABLE_PROFILING=1 set by default.

The test for disabled profiling is in test_e2e.py where it uses the
standard production container without profiling tools.
"""

import os
import subprocess
import time
from collections.abc import Generator

import httpx
import pytest


@pytest.fixture(scope="module")
def docker_compose_with_profiling() -> Generator[None, None, None]:
    """Bring up Docker Compose with profiling container for testing.

    This fixture uses the profiling container variant which includes
    pyinstrument and has ENABLE_PROFILING=1 set by default.
    Scoped to module to reuse the same container instance across all profiling tests.
    """
    env = os.environ.copy()
    # Use test-specific volume
    env["BIRDNET_DATA_VOLUME"] = "birdnet-test-data"

    compose_cmd = ["docker", "compose"]

    # Bring up the profiling container using the profile
    subprocess.run(
        compose_cmd + ["--profile", "profiling", "up", "-d", "--build"], env=env, check=True
    )

    # Wait for services to be ready
    for attempt in range(30):
        try:
            response = httpx.get("http://localhost:8000/api/health/ready", timeout=3)
            if response.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        # Clean up on failure
        subprocess.run(compose_cmd + ["--profile", "profiling", "down"], env=env, check=False)
        pytest.fail("Services did not become ready in time")

    yield

    # Tear down services (preserves test volume)
    subprocess.run(compose_cmd + ["--profile", "profiling", "down"], env=env, check=True)


@pytest.mark.expensive
def test_profiling_enabled_root_page(docker_compose_with_profiling) -> None:
    """Test that profiling works on the root page when enabled."""
    # Request the root page with ?profile=1
    response = httpx.get("http://localhost:8000/?profile=1")
    assert response.status_code == 200

    # Should contain pyinstrument profiling output
    assert "pyinstrument" in response.text.lower()

    # Check for key profiling elements
    assert "cpu utilization" in response.text.lower() or "samples" in response.text.lower()

    # Should show the function being profiled
    assert "read_root" in response.text or "factory.py" in response.text

    # Should have timing information
    assert "ms" in response.text or "s" in response.text  # milliseconds or seconds


@pytest.mark.expensive
def test_profiling_enabled_settings_page(docker_compose_with_profiling) -> None:
    """Test that profiling works on the settings page when enabled.

    The settings page is ideal for testing because it doesn't call
    get_cpu_usage() or other system monitoring functions that have
    inherent delays, providing a cleaner profiling output.
    """
    # Request the settings page with ?profile=1
    response = httpx.get("http://localhost:8000/admin/settings?profile=1")
    assert response.status_code == 200

    # Should contain pyinstrument profiling output
    assert "pyinstrument" in response.text.lower()

    # Should show the settings route or admin functions
    assert "admin" in response.text.lower() or "settings" in response.text.lower()

    # Should have performance metrics
    assert any(keyword in response.text.lower() for keyword in ["cpu", "samples", "utilization"])


@pytest.mark.expensive
def test_profiling_shows_system_calls(docker_compose_with_profiling) -> None:
    """Test that profiling output shows expected system calls for dashboard."""
    # Request the root page (dashboard) with profiling
    response = httpx.get("http://localhost:8000/?profile=1")
    assert response.status_code == 200

    # Should show our optimized get_system_info call
    assert "get_system_info" in response.text or "SystemInspector" in response.text

    # Should show presentation manager methods
    assert "PresentationManager" in response.text or "get_landing_page" in response.text.lower()

    # Should NOT show multiple get_cpu_usage calls (our optimization)
    # Count occurrences of get_cpu_usage - should be at most 1
    cpu_usage_count = response.text.count("get_cpu_usage")
    assert cpu_usage_count <= 1, f"Found {cpu_usage_count} calls to get_cpu_usage, expected <= 1"


@pytest.mark.expensive
def test_profiling_normal_request_unaffected(docker_compose_with_profiling) -> None:
    """Test that requests without ?profile=1 work normally when profiling is enabled."""
    # Request without profiling parameter
    response = httpx.get("http://localhost:8000/")
    assert response.status_code == 200

    # Should return normal page content
    assert "BirdNET-Pi" in response.text

    # Should NOT contain profiling output
    assert "pyinstrument" not in response.text.lower()
    assert "flame" not in response.text.lower()

    # Page should have normal HTML structure
    assert "<html" in response.text.lower() or "<!doctype" in response.text.lower()


@pytest.mark.expensive
def test_profiling_api_endpoints(docker_compose_with_profiling) -> None:
    """Test that profiling works on API endpoints."""
    # Test a simple API endpoint with profiling
    response = httpx.get("http://localhost:8000/api/health/ready?profile=1")
    assert response.status_code == 200

    # Should contain profiling output instead of JSON
    assert "pyinstrument" in response.text.lower()

    # Should show the health check function
    assert "health" in response.text.lower() or "ready" in response.text.lower()
