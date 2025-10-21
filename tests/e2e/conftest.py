"""E2E test fixtures for BirdNET-Pi."""

import os
import subprocess
import time
from collections.abc import Generator

import httpx
import pytest

from birdnetpi.releases.asset_manifest import AssetManifest
from birdnetpi.system.path_resolver import PathResolver


@pytest.fixture(scope="module")
def docker_compose_up_down() -> Generator[None, None, None]:
    """Bring up and tear down Docker Compose services for e2e tests.

    Uses the main docker-compose.yml with a test-specific volume name.
    This allows us to preserve expensive downloads between test runs
    while still cleaning the test database.

    The cleanup phase uses AssetManifest to identify which paths should be preserved
    during cleanup (models, IOC database, etc.) and removes everything else.

    CRITICAL: Uses BIRDNET_DATA_VOLUME environment variable to work with test volume.
    NEVER use 'docker-compose down -v' as it removes ALL volumes including production data!
    """
    env = os.environ.copy()
    # Use a test-specific volume name to isolate test data
    env["BIRDNET_DATA_VOLUME"] = "birdnet-test-data"

    # Use the main compose file with environment variable
    compose_cmd = ["docker", "compose"]

    # Bring up Docker Compose (without --wait to avoid health check timeout issues in CI)
    # Note: --build removed because images are pre-built in CI workflow
    subprocess.run([*compose_cmd, "up", "-d"], env=env, check=True)

    # Wait for services to be ready by polling the health endpoint
    # This is more forgiving than Docker health checks and provides better diagnostics
    for _attempt in range(30):
        try:
            response = httpx.get("http://localhost:8000/api/health/ready", timeout=3)
            if response.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        # Clean up on failure
        print("\nServices did not become ready in time. Container logs:")
        subprocess.run(["docker", "ps", "-a"], check=False)
        subprocess.run(["docker", "compose", "logs"], check=False, env=env)
        subprocess.run([*compose_cmd, "down"], env=env, check=False)
        pytest.fail("Services did not become ready in time")

    yield

    # Bring down Docker Compose but keep the volume to preserve models
    subprocess.run([*compose_cmd, "down"], check=True, env=env)

    # Clean up Docker test environment while preserving expensive assets
    print("\nCleaning up Docker test environment...")

    # Create a PathResolver configured for the Docker volume mount point
    # We need to know what paths are protected
    old_env_data = os.environ.get("BIRDNETPI_DATA")
    os.environ["BIRDNETPI_DATA"] = "/data"
    path_resolver = PathResolver()

    # Get protected paths from AssetManifest
    protected_paths = AssetManifest.get_protected_paths(path_resolver)
    protected_path_strings = [str(p) for p in protected_paths]

    # Restore environment
    if old_env_data is not None:
        os.environ["BIRDNETPI_DATA"] = old_env_data
    else:
        os.environ.pop("BIRDNETPI_DATA", None)

    # Build a cleanup script that will run inside a container
    protected_paths_str = " ".join(protected_path_strings)
    cleanup_script = f"""#!/bin/sh
set -e

echo "Starting Docker volume cleanup..."

# Function to check if a path is protected
is_protected() {{
    path="$1"
    for protected in {protected_paths_str}; do
        # Check if path matches or is inside a protected directory
        case "$path" in
            "$protected"|"$protected/"*) return 0 ;;
        esac
    done
    return 1
}}

# Clean up test data while preserving assets
cd /data 2>/dev/null || exit 0

# Remove runtime database (not protected)
rm -f /data/database/birdnetpi.db
echo "  Removed runtime database"

# Remove test databases
rm -f /data/database/test_*.db
echo "  Removed test databases"

# Remove recordings directory
rm -rf /data/recordings
echo "  Removed recordings"

# Remove exports directory
rm -rf /data/exports
echo "  Removed exports"

# Clean up other non-protected files
find /data -type f | while read -r file; do
    if ! is_protected "$file"; then
        rm -f "$file" 2>/dev/null && echo "  Removed: $file"
    fi
done

# Remove empty directories (bottom-up)
find /data -depth -type d -empty | while read -r dir; do
    if ! is_protected "$dir"; then
        rmdir "$dir" 2>/dev/null && echo "  Removed empty dir: $dir"
    fi
done

echo "Docker cleanup completed. Assets preserved."
"""

    # Run cleanup script in an Alpine container with access to the volume
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                "birdnet-test-data:/data",
                "alpine",
                "sh",
                "-c",
                cleanup_script,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(f"Cleanup warnings: {result.stderr}")

    except Exception as e:
        print(f"Warning: Failed to run Docker cleanup: {e}")
        print("The volume may need manual cleanup")


# Keep the docker_cleanup fixture for backward compatibility if needed
@pytest.fixture
def docker_cleanup():
    """Legacy fixture for docker cleanup - now integrated into docker_compose_up_down."""
    # This is now a no-op since cleanup is handled in docker_compose_up_down
    yield
