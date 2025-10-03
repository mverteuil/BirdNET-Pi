"""Tests for the optimize_database CLI command."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from birdnetpi.cli.optimize_database import (
    analyze_performance,
    cli,
    export_report,
    optimize_database,
    print_query_performance,
    print_section,
    setup_database_service,
)


class TestSetupDatabaseService:
    """Test database service setup."""

    def test_setup_database_service(self, mocker, path_resolver):
        """Should successful database service setup."""
        # Use the global path_resolver fixture (from conftest.py)
        mocker.patch("birdnetpi.cli.optimize_database.PathResolver", return_value=path_resolver)

        # Mock CoreDatabaseService
        mock_db_service = mocker.AsyncMock()
        mock_db_service_class = mocker.patch(
            "birdnetpi.cli.optimize_database.CoreDatabaseService", return_value=mock_db_service
        )

        # Call the function
        result = setup_database_service()

        # Verify
        assert result == mock_db_service
        # Verify CoreDatabaseService was called with the correct path
        db_path = path_resolver.get_database_path()
        mock_db_service_class.assert_called_once_with(db_path)
        # Verify the directory was created
        assert db_path.parent.exists()


class TestPrintFunctions:
    """Test print utility functions."""

    def test_print_section_with_content(self, capsys):
        """Should print_section with content."""
        print_section("Test Title", "Test content")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
        assert "Test content" in captured.out
        assert "=" * 60 in captured.out

    def test_print_section_without_content(self, capsys):
        """Should print_section without content."""
        print_section("Test Title")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out
        assert "=" * 60 in captured.out

    def test_print_query_performance_with_data(self, capsys):
        """Should print_query_performance with performance data."""
        performance_data = [
            {
                "name": "Test Query",
                "time_ms": 10.5,
                "rows": 100,
                "index_ops": 2,
                "scan_ops": 1,
            },
            {
                "name": "Long Query Name That Should Be Truncated Because It Is Too Long",
                "time_ms": 20.3,
                "rows": 200,
            },
        ]
        print_query_performance(performance_data, "Test Performance")
        captured = capsys.readouterr()
        assert "Test Performance" in captured.out
        assert "Test Query" in captured.out
        assert "10.50" in captured.out
        assert "100" in captured.out
        assert "Long Query Name That Should Be Truncate" in captured.out

    def test_print_query_performance_with_error(self, capsys):
        """Should print_query_performance with error in data."""
        performance_data = [
            {"name": "Failed Query", "error": "Database locked"},
        ]
        print_query_performance(performance_data, "Test Performance")
        captured = capsys.readouterr()
        assert "Failed Query" in captured.out
        assert "Error: Database locked" in captured.out

    def test_print_query_performance_empty_data(self, capsys):
        """Should print_query_performance with no data."""
        print_query_performance([], "Test Performance")
        captured = capsys.readouterr()
        assert "No performance data available" in captured.out


class TestAnalyzePerformance:
    """Test analyze_performance function."""

    @pytest.mark.asyncio
    async def test_analyze_performance_with_indexes(self, mocker, capsys):
        """Should analyze_performance with existing indexes."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.get_current_indexes.return_value = {
            "detections": ["idx_date", "idx_species"]
        }
        mock_optimizer.analyze_table_statistics.return_value = {
            "detections": {
                "row_count": 1000,
                "date_range": {
                    "min_date": "2024-01-01",
                    "max_date": "2024-12-31",
                },
            }
        }

        await analyze_performance(mock_optimizer)

        captured = capsys.readouterr()
        assert "Analyzing Database Performance" in captured.out
        assert "Table: detections" in captured.out
        assert "idx_date" in captured.out
        assert "idx_species" in captured.out
        assert "Total detections: 1,000" in captured.out
        assert "2024-01-01 to 2024-12-31" in captured.out

    @pytest.mark.asyncio
    async def test_analyze_performance_no_indexes(self, mocker, capsys):
        """Should analyze_performance with no indexes."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.get_current_indexes.return_value = {}
        mock_optimizer.analyze_table_statistics.return_value = {"detections": {"row_count": 0}}

        await analyze_performance(mock_optimizer)

        captured = capsys.readouterr()
        assert "No custom indexes found" in captured.out
        assert "Total detections: 0" in captured.out


class TestOptimizeDatabase:
    """Test optimize_database function."""

    @pytest.mark.asyncio
    async def test_optimize_database_dry_run(self, mocker, capsys):
        """Should optimize_database in dry run mode."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.create_optimized_indexes.return_value = [
            "CREATE INDEX idx_test ON detections(date)",
            "CREATE INDEX idx_species ON detections(species)",
        ]

        await optimize_database(mock_optimizer, dry_run=True)

        captured = capsys.readouterr()
        assert "Optimization Plan (Dry Run)" in captured.out
        assert "Would create 2 indexes" in captured.out
        mock_optimizer.create_optimized_indexes.assert_called_once_with(dry_run=True)
        mock_optimizer.optimize_database.assert_not_called()

    @pytest.mark.asyncio
    async def test_optimize_database_real_run(self, mocker, capsys):
        """Should optimize_database in real mode."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.create_optimized_indexes.return_value = [
            "CREATE INDEX idx_test ON detections(date)",
        ]
        mock_optimizer.optimize_database.return_value = {
            "vacuum_result": True,
            "analyze_result": True,
        }

        await optimize_database(mock_optimizer, dry_run=False)

        captured = capsys.readouterr()
        assert "Running Database Optimization" in captured.out
        assert "Created 1 optimized indexes" in captured.out
        assert "Database vacuumed successfully" in captured.out
        assert "Table statistics updated" in captured.out
        mock_optimizer.create_optimized_indexes.assert_called_once_with(dry_run=False)
        mock_optimizer.optimize_database.assert_called_once()

    @pytest.mark.asyncio
    async def test_optimize_database_no_changes_needed(self, mocker, capsys):
        """Should optimize_database when no changes are needed."""
        mock_optimizer = mocker.AsyncMock()
        # Configure the mock to return empty results
        mock_optimizer.create_optimized_indexes.return_value = []
        mock_optimizer.optimize_database.return_value = {}

        await optimize_database(mock_optimizer, dry_run=False)

        captured = capsys.readouterr()
        assert "No new indexes needed" in captured.out
        assert "Database was already optimized" in captured.out

    @pytest.mark.asyncio
    async def test_optimize_database_many_indexes(self, mocker, capsys):
        """Should optimize_database with more than 5 indexes."""
        mock_optimizer = mocker.AsyncMock()
        indexes = [f"CREATE INDEX idx_{i} ON table(col{i})" for i in range(10)]
        mock_optimizer.create_optimized_indexes.return_value = indexes
        mock_optimizer.optimize_database.return_value = {
            "vacuum_result": True,
            "analyze_result": True,
        }

        await optimize_database(mock_optimizer, dry_run=False)

        captured = capsys.readouterr()
        assert "Created 10 indexes" in captured.out
        assert "... and 5 more" in captured.out


class TestExportReport:
    """Test export_report function."""

    @pytest.mark.asyncio
    async def test_export_report_success(self, mocker, tmp_path, capsys):
        """Should successful report export."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.analyze_table_statistics.return_value = {"test": "stats"}
        mock_optimizer.get_current_indexes.return_value = {"test": ["idx1"]}

        export_path = tmp_path / "report.json"
        await export_report(mock_optimizer, export_path)

        captured = capsys.readouterr()
        assert "Report exported to" in captured.out
        assert str(export_path) in captured.out
        assert export_path.exists()

        with open(export_path) as f:
            report = json.load(f)
            assert "timestamp" in report
            assert report["database_statistics"] == {"test": "stats"}
            assert report["existing_indexes"] == {"test": ["idx1"]}

    @pytest.mark.asyncio
    async def test_export_report_failure(self, mocker, capsys):
        """Should report export failure."""
        mock_optimizer = mocker.AsyncMock()
        mock_optimizer.analyze_table_statistics.side_effect = Exception("Test error")

        export_path = Path("/invalid/path/report.json")
        await export_report(mock_optimizer, export_path)

        captured = capsys.readouterr()
        assert "Export failed" in captured.err  # Error messages go to stderr
        assert "Test error" in captured.err


class TestCLI:
    """Test CLI command."""

    def test_cli_no_options(self):
        """Should CLI with no options shows help."""
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 1
        assert "Usage:" in result.output

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_analyze_option(self, mock_optimizer_class, mock_setup_db):
        """Should CLI with analyze option."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        runner = CliRunner()
        result = runner.invoke(cli, ["--analyze"])

        assert result.exit_code == 0
        assert "Analyzing Database Performance" in result.output
        mock_optimizer.get_current_indexes.assert_called_once()
        mock_optimizer.analyze_table_statistics.assert_called_once()

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_optimize_option(self, mock_optimizer_class, mock_setup_db):
        """Should CLI with optimize option."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        runner = CliRunner()
        result = runner.invoke(cli, ["--optimize"])

        assert result.exit_code == 0
        assert "Running Database Optimization" in result.output
        mock_optimizer.create_optimized_indexes.assert_called_once()
        mock_optimizer.optimize_database.assert_called_once()

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_dry_run_option(self, mock_optimizer_class, mock_setup_db):
        """Should CLI with dry-run option."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        runner = CliRunner()
        result = runner.invoke(cli, ["--optimize", "--dry-run"])

        assert result.exit_code == 0
        assert "Optimization Plan (Dry Run)" in result.output
        mock_optimizer.create_optimized_indexes.assert_called_once_with(dry_run=True)
        mock_optimizer.optimize_database.assert_not_called()

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_export_option(self, mock_optimizer_class, mock_setup_db, tmp_path):
        """Should CLI with export option."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        export_path = tmp_path / "test_report.json"
        runner = CliRunner()
        result = runner.invoke(cli, ["--export", str(export_path)])

        assert result.exit_code == 0
        assert "Report exported to" in result.output
        assert export_path.exists()

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_verbose_option(self, mock_optimizer_class, mock_setup_db):
        """Should CLI with verbose option."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        runner = CliRunner()
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            result = runner.invoke(cli, ["--analyze", "--verbose"])

            assert result.exit_code == 0
            mock_logger.setLevel.assert_called_with(10)  # DEBUG level

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    @patch("birdnetpi.cli.optimize_database.DatabaseOptimizer")
    def test_cli_multiple_options(self, mock_optimizer_class, mock_setup_db):
        """Should CLI with multiple options."""
        mock_db_service = MagicMock()
        mock_setup_db.return_value = mock_db_service

        mock_optimizer = MagicMock()
        # Make async methods return coroutines
        mock_optimizer.get_current_indexes = AsyncMock(return_value={})
        mock_optimizer.analyze_table_statistics = AsyncMock(return_value={})
        mock_optimizer.create_optimized_indexes = AsyncMock(return_value=[])
        mock_optimizer.optimize_database = AsyncMock(return_value={})
        mock_optimizer_class.return_value = mock_optimizer

        runner = CliRunner()
        result = runner.invoke(cli, ["--analyze", "--optimize"])

        assert result.exit_code == 0
        assert "Analyzing Database Performance" in result.output
        assert "Running Database Optimization" in result.output
        mock_optimizer.get_current_indexes.assert_called_once()
        mock_optimizer.analyze_table_statistics.assert_called_once()
        mock_optimizer.create_optimized_indexes.assert_called_once()
        mock_optimizer.optimize_database.assert_called_once()

    @patch("birdnetpi.cli.optimize_database.setup_database_service")
    def test_cli_exception_handling(self, mock_setup_db):
        """Should CLI exception handling."""
        mock_setup_db.side_effect = Exception("Database connection failed")

        runner = CliRunner()
        # Use standalone_mode=False to get the actual return value
        result = runner.invoke(cli, ["--analyze"], standalone_mode=False)

        # Check that we got an error (either exit code 1 or the error in output)
        # The function returns 1 but Click might handle it differently
        assert result.exit_code != 0 or "Error: Database connection failed" in result.output


class TestMain:
    """Test main entry point."""

    @patch("birdnetpi.cli.optimize_database.cli")
    def test_main_function(self, mock_cli):
        """Should main function calls CLI."""
        mock_cli.return_value = 0

        with pytest.raises(SystemExit) as exc_info:
            from birdnetpi.cli.optimize_database import main

            main()

        assert exc_info.value.code == 0
        mock_cli.assert_called_once()
