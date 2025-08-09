"""Common fixtures for web application tests."""

import os
from pathlib import Path
from typing import Any

import pytest

from birdnetpi.web.core.factory import create_app


@pytest.fixture
def app_with_temp_data(tmp_path: Path) -> Any:
    """Create FastAPI app with temp data directory.

    This fixture ensures that all database connections use temporary directories
    instead of the real data directory, preventing database lock issues and
    cross-test contamination.
    """
    # Store original environment variable
    original_data_env = os.environ.get("BIRDNETPI_DATA")

    try:
        # Set environment variable to temp path BEFORE creating any services
        os.environ["BIRDNETPI_DATA"] = str(tmp_path)

        app = create_app()
        return app

    finally:
        # Restore original environment variable
        if original_data_env is not None:
            os.environ["BIRDNETPI_DATA"] = original_data_env
        else:
            os.environ.pop("BIRDNETPI_DATA", None)
