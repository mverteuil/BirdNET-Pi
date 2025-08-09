from pathlib import Path

import matplotlib
import pytest

from birdnetpi.utils.file_path_resolver import FilePathResolver

# Configure matplotlib to use non-GUI backend for testing
matplotlib.use("Agg")

# Pyleak is available for manual use in tests via @pytest.mark.no_leaks
# The pytest plugin automatically handles this when tests are marked with @pytest.mark.no_leaks


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """Provide a FilePathResolver with proper separation of read-only and writable paths.

    IMPORTANT: This fixture properly isolates test data by:
    1. Using REAL repo paths for READ-ONLY assets that tests need to access:
       - Models (*.tflite files)
       - IOC reference database
       - Avibase multilingual database
       - PatLevin labels database
       - Static files (CSS, JS, images)
       - Templates (HTML templates)
       - Config template (birdnetpi.yaml.template)

    2. Using TEMP paths for WRITABLE data to prevent test pollution:
       - Main database (birdnetpi.db) - prevents tests from writing to data/database/
       - Config file (birdnetpi.yaml) - prevents tests from writing to data/config/
       - Log files - prevents tests from writing to data/logs/
       - Export files - prevents tests from writing to data/exports/

    This separation is critical because:
    - Tests need real assets (models, IOC db) to function properly
    - Tests must NOT write to the real data/ directory (would pollute the repo)
    - FilePathResolver has individual methods for each path type specifically
      to enable this kind of mocking/overriding

    DO NOT use environment variables to control paths - that approach fails because
    it affects ALL paths uniformly, when we need selective path overriding.
    """
    from pathlib import Path
    from unittest.mock import patch

    project_root = Path(__file__).parent.parent
    real_data_dir = project_root / "data"
    real_app_dir = project_root

    # Create resolver with real paths
    resolver = FilePathResolver()

    # Create temp directories for writable data
    temp_database_dir = tmp_path / "database"
    temp_database_dir.mkdir(parents=True)
    temp_config_dir = tmp_path / "config"
    temp_config_dir.mkdir(parents=True)
    temp_logs_dir = tmp_path / "logs"
    temp_logs_dir.mkdir(parents=True)
    temp_exports_dir = tmp_path / "exports"
    temp_exports_dir.mkdir(parents=True)

    # Override WRITABLE paths to use temp directory
    resolver.get_database_path = lambda: str(temp_database_dir / "birdnetpi.db")
    resolver.get_birdnetpi_config_path = lambda: str(temp_config_dir / "birdnetpi.yaml")
    resolver.get_logs_dir = lambda: str(temp_logs_dir)
    resolver.get_exports_dir = lambda: str(temp_exports_dir)

    # Keep READ-ONLY paths pointing to real repo locations
    # These are already correct from the base FilePathResolver, but let's be explicit:
    resolver.get_ioc_database_path = lambda: str(real_data_dir / "database" / "ioc_reference.db")
    resolver.get_avibase_database_path = lambda: str(
        real_data_dir / "database" / "avibase_database.db"
    )
    resolver.get_patlevin_database_path = lambda: str(
        real_data_dir / "database" / "patlevin_database.db"
    )
    resolver.get_models_dir = lambda: str(real_data_dir / "models")
    resolver.get_model_path = lambda model_filename: str(
        real_data_dir
        / "models"
        / (model_filename if model_filename.endswith(".tflite") else f"{model_filename}.tflite")
    )
    resolver.get_config_template_path = lambda: str(
        real_app_dir / "config" / "birdnetpi.yaml.template"
    )
    resolver.get_static_dir = lambda: str(real_app_dir / "static")
    resolver.get_templates_dir = lambda: str(real_app_dir / "templates")

    # For config tests, copy template to temp config location
    template_path = Path(resolver.get_config_template_path())
    if template_path.exists():
        config_path = Path(resolver.get_birdnetpi_config_path())
        config_path.write_text(template_path.read_text())

    return resolver


@pytest.fixture
def test_config(file_path_resolver: FilePathResolver):
    """Load test configuration from the test config file."""
    from birdnetpi.utils.config_file_parser import ConfigFileParser

    parser = ConfigFileParser(file_path_resolver.get_birdnetpi_config_path())
    return parser.load_config()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment.

    This fixture ensures that any test creating FilePathResolver without
    using the file_path_resolver fixture will still work properly.
    """
    # Currently a no-op, but kept for potential future session-level setup
    yield


@pytest.fixture(scope="session", autouse=True)
def check_required_assets():
    """Check that required assets are available for testing."""
    from pathlib import Path

    # Get project root directory
    project_root = Path(__file__).parent.parent
    real_data_dir = project_root / "data"
    missing_assets = []

    # Check for model files
    models_dir = real_data_dir / "models"
    if not models_dir.exists() or not any(models_dir.glob("*.tflite")):
        missing_assets.append("Model files (*.tflite)")

    # Note: labels.txt is legacy - IOC database is now used for bird species names

    # Check for IOC database
    ioc_db_path = real_data_dir / "database" / "ioc_reference.db"
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
