"""Test the backfill-weather CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from birdnetpi.cli.backfill_weather import _display_stats, backfill_weather
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.location.weather import WeatherManager


def test_backfill_weather_help():
    """Should help text displays correctly."""
    runner = CliRunner()
    result = runner.invoke(backfill_weather, ["--help"])
    assert result.exit_code == 0
    assert "Backfill weather data for detections" in result.output
    assert "--start" in result.output
    assert "--end" in result.output
    assert "--days" in result.output
    assert "--force" in result.output
    assert "--smart" in result.output


@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_no_location(mock_load, mock_db, path_resolver, test_config):
    """Should error when location is not configured."""
    # Mock config without location
    test_config.latitude = None
    test_config.longitude = None
    mock_load.return_value = test_config

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--days", "7"])

        assert result.exit_code == 0
        assert "Latitude and longitude must be configured" in result.output


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_days_option(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should backfilling with --days option."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.backfill_weather_bulk = AsyncMock(
        spec=WeatherManager.backfill_weather_bulk,
        return_value={
            "total_days": 7,
            "api_calls": 1,
            "records_created": 168,
            "detections_updated": 50,
        },
    )
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--days", "7"])

        assert result.exit_code == 0
        assert "Backfilling 7 days" in result.output
        assert "Backfill Complete!" in result.output
        assert "50 detections to weather data" in result.output


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_date_range(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should backfilling with specific date range."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.backfill_weather_bulk = AsyncMock(
        spec=WeatherManager.backfill_weather_bulk,
        return_value={
            "total_days": 31,
            "api_calls": 3,
            "records_created": 744,
            "detections_updated": 150,
        },
    )
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(
            backfill_weather,
            ["--start", "2024-01-01", "--end", "2024-01-31"],
        )

        assert result.exit_code == 0
        assert "Backfilling from 2024-01-01" in result.output
        assert "to 2024-01-31" in result.output
        assert "API calls made: 3" in result.output
        assert "Weather records created: 744" in result.output


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_smart_mode(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should smart backfill mode."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.smart_backfill = AsyncMock(
        spec=WeatherManager.smart_backfill,
        return_value={
            "total_days": 5,
            "api_calls": 1,
            "records_created": 120,
            "detections_updated": 75,
        },
    )
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--smart"])

        assert result.exit_code == 0
        assert "Starting smart backfill" in result.output
        assert "detections without weather" in result.output
        assert "Backfill Complete!" in result.output


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_smart_no_detections(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should skip backfill when no detections need weather data."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.smart_backfill = AsyncMock(
        spec=WeatherManager.smart_backfill,
        return_value={"message": "No detections need weather data"},
    )
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--smart"])

        assert result.exit_code == 0
        assert "No detections need weather data" in result.output


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_force_option(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should force re-fetch option."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.backfill_weather_bulk = AsyncMock(
        spec=WeatherManager.backfill_weather_bulk,
        return_value={
            "total_days": 3,
            "api_calls": 1,
            "records_created": 72,
            "detections_updated": 20,
        },
    )
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--days", "3", "--force"])

        assert result.exit_code == 0
        assert "Skip existing: False" in result.output

        # Verify that skip_existing=False was passed
        mock_weather_instance.backfill_weather_bulk.assert_called_once()
        call_kwargs = mock_weather_instance.backfill_weather_bulk.call_args.kwargs
        assert call_kwargs["skip_existing"] is False


@patch("birdnetpi.cli.backfill_weather.WeatherManager", autospec=True)
@patch("birdnetpi.cli.backfill_weather.CoreDatabaseService", autospec=True)
@patch("birdnetpi.cli.backfill_weather.ConfigManager.load", autospec=True)
def test_backfill_weather_no_bulk_option(
    mock_load, mock_db, mock_weather_manager, path_resolver, test_config
):
    """Should non-bulk backfill mode."""
    # Setup mocks
    mock_load.return_value = test_config

    mock_weather_instance = MagicMock(spec=WeatherManager)
    mock_weather_instance.backfill_weather = AsyncMock(
        spec=WeatherManager.backfill_weather,
        return_value={
            "total_hours": 24,
            "fetched": 24,
            "skipped": 0,
            "errors": 0,
            "detections_updated": 10,
        },
    )
    mock_weather_instance.backfill_weather_bulk = AsyncMock(
        spec=lambda: None
    )  # Need this for assert_not_called
    mock_weather_manager.return_value = mock_weather_instance

    # Mock database service methods
    mock_db_instance = MagicMock(spec=CoreDatabaseService)
    mock_db_instance.initialize = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db = MagicMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aenter__ = AsyncMock(spec=lambda: None)
    mock_db_instance.get_async_db.return_value.__aexit__ = AsyncMock(spec=lambda: None)
    mock_db_instance.dispose = AsyncMock(spec=lambda: None)
    mock_db.return_value = mock_db_instance

    # Patch PathResolver with the global fixture
    with patch("birdnetpi.cli.backfill_weather.PathResolver", autospec=True) as mock_path:
        mock_path.return_value = path_resolver

        runner = CliRunner()
        result = runner.invoke(backfill_weather, ["--days", "1", "--no-bulk"])

        assert result.exit_code == 0
        assert "Total hours processed: 24" in result.output
        assert "Weather fetched: 24" in result.output

        # Verify that regular backfill was called, not bulk
        mock_weather_instance.backfill_weather.assert_called_once()
        mock_weather_instance.backfill_weather_bulk.assert_not_called()


def test_display_stats_hourly():
    """Should display of hourly backfill statistics."""
    stats = {
        "total_hours": 48,
        "fetched": 45,
        "skipped": 3,
        "errors": 2,
        "detections_updated": 100,
    }

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Capture output
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        _display_stats(stats)

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()

        assert "Total hours processed: 48" in output
        assert "Weather fetched: 45" in output
        assert "Skipped (existing): 3" in output
        assert "Errors: 2" in output
        assert "2 errors occurred during backfill" in output
        assert "100 detections to weather data" in output


def test_display_stats_bulk():
    """Should display of bulk backfill statistics."""
    stats = {
        "total_days": 7,
        "api_calls": 1,
        "records_created": 168,
        "detections_updated": 250,
    }

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Capture output
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        _display_stats(stats)

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()

        assert "Total days processed: 7" in output
        assert "API calls made: 1" in output
        assert "Weather records created: 168" in output
        assert "250 detections to weather data" in output


def test_display_stats_no_updates():
    """Should display when no detections were updated."""
    stats = {
        "total_hours": 24,
        "fetched": 24,
        "skipped": 0,
        "errors": 0,
        "detections_updated": 0,
    }

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Capture output
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        _display_stats(stats)

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()

        assert "No detections were updated" in output
        assert "may already have weather data" in output
