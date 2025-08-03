from pathlib import Path

import matplotlib
import pytest
from pyleak import no_task_leaks, no_thread_leaks, no_event_loop_blocking

from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")

# Pyleak is available for manual use in tests via @pytest.mark.no_leaks
# The pytest plugin automatically handles this when tests are marked with @pytest.mark.no_leaks


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with temp data_dir and explicit real repo overrides.

    All data paths go to temp by default (robust against new path methods).
    Explicitly override paths that should use real repo locations.
    """
    resolver = FilePathResolver()

    # Override the core data_dir to point to temp - this makes ALL data paths go to temp by default
    resolver.data_dir = tmp_path

    # Point config to the template file
    resolver.get_birdnetpi_config_path = lambda: resolver.get_config_template_path()

    # EXPLICIT OVERRIDES: paths that should use real repo locations
    from pathlib import Path

    project_root = Path(__file__).parent.parent
    real_data_dir = project_root / "data"

    # IOC database - use real repo path
    resolver.get_ioc_database_path = lambda: str(real_data_dir / "database" / "ioc_reference.db")

    # Models - use real repo path
    resolver.get_models_dir = lambda: str(real_data_dir / "models")
    resolver.get_model_path = lambda model_filename: str(
        real_data_dir
        / "models"
        / (model_filename if model_filename.endswith(".tflite") else f"{model_filename}.tflite")
    )

    return resolver


@pytest.fixture
def test_config(file_path_resolver: FilePathResolver):
    """Load test configuration from the test config file."""
    from birdnetpi.utils.config_file_parser import ConfigFileParser

    parser = ConfigFileParser(file_path_resolver.get_birdnetpi_config_path())
    return parser.load_config()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment with proper paths to repo data directory."""
    import os
    from pathlib import Path

    # Get project root directory
    project_root = Path(__file__).parent.parent

    # Store original environment variables
    original_app_env = os.environ.get("BIRDNETPI_APP")
    original_data_env = os.environ.get("BIRDNETPI_DATA")

    # Set environment variables to point to real repo directories for the entire test session
    os.environ["BIRDNETPI_APP"] = str(project_root)
    os.environ["BIRDNETPI_DATA"] = str(project_root / "data")

    yield

    # Restore original environment variables
    if original_app_env is not None:
        os.environ["BIRDNETPI_APP"] = original_app_env
    else:
        os.environ.pop("BIRDNETPI_APP", None)

    if original_data_env is not None:
        os.environ["BIRDNETPI_DATA"] = original_data_env
    else:
        os.environ.pop("BIRDNETPI_DATA", None)


@pytest.fixture(scope="session", autouse=True)
def check_required_assets():
    """Check that required assets are available for testing."""
    from pathlib import Path

    from birdnetpi.utils.file_path_resolver import FilePathResolver

    file_resolver = FilePathResolver()
    missing_assets = []

    # Check for model files
    models_dir = Path(file_resolver.get_models_dir())
    if not models_dir.exists() or not any(models_dir.glob("*.tflite")):
        missing_assets.append("Model files (*.tflite)")

    # Note: labels.txt is legacy - IOC database is now used for bird species names

    # Check for IOC database
    ioc_db_path = Path(file_resolver.get_ioc_database_path())
    if not ioc_db_path.exists():
        missing_assets.append("IOC reference database")

    if missing_assets:
        print()
        print("┌" + "─" * 78 + "┐")
        print("│" + " " * 78 + "│")
        print("│  ⚠️  MISSING ASSETS FOR TESTING" + " " * 45 + "│")
        print("│" + " " * 78 + "│")
        print("│  The following required assets are missing for testing:" + " " * 22 + "│")
        for asset in missing_assets:
            spaces_needed = 76 - len(f"│    • {asset}")
            print(f"│    • {asset}" + " " * spaces_needed + "│")
        print("│" + " " * 78 + "│")
        print("│  To run tests with assets, install them first:" + " " * 29 + "│")
        print("│    export BIRDNETPI_DATA=./data" + " " * 43 + "│")
        print("│    uv run asset-installer install v2.1.0 --include-models --include-ioc-db│")
        print("│" + " " * 78 + "│")
        print("│  Most tests will still pass without assets (mocked dependencies)." + " " * 9 + "│")
        print(
            "│  Only integration tests and some service tests require real assets." + " " * 10 + "│"
        )
        print("│" + " " * 78 + "│")
        print("└" + "─" * 78 + "┘")
        print()
