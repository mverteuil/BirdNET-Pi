#!/usr/bin/env python3
"""Command-line tool for optimizing the BirdNET-Pi database for analytics queries.

This script provides database optimization capabilities including:
- Creating optimized indexes for common query patterns
- Analyzing query performance
- Generating optimization recommendations
- Monitoring database health
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from birdnetpi.database.database_optimizer import DatabaseOptimizer
from birdnetpi.database.database_service import DatabaseService
from birdnetpi.system.path_resolver import PathResolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_database_service() -> DatabaseService:
    """Set up database service with proper configuration.

    Returns:
        Configured DatabaseService instance
    """
    resolver = PathResolver()
    db_path = resolver.get_database_path()

    # Ensure database directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return DatabaseService(db_path)


def print_section(title: str, content: str = "") -> None:
    """Print a formatted section header.

    Args:
        title: Section title
        content: Optional content to print after header
    """
    click.echo(f"\n{'=' * 60}")
    click.echo(f" {title}")
    click.echo(f"{'=' * 60}")
    if content:
        click.echo(content)


def print_query_performance(performance_data: list, title: str) -> None:
    """Print query performance results in a formatted table.

    Args:
        performance_data: List of query performance dictionaries
        title: Table title
    """
    print_section(title)

    if not performance_data:
        click.echo("No performance data available.")
        return

    # Print table header
    click.echo(f"{'Query Name':<40} {'Time (ms)':<12} {'Rows':<8} {'Index':<8} {'Scan':<8}")
    click.echo("-" * 80)

    # Print each query's performance
    for query in performance_data:
        if "error" in query:
            click.echo(f"{query['name']:<40} Error: {query['error']}")
        else:
            name = query["name"][:39]
            time_ms = f"{query['time_ms']:.2f}"
            rows = str(query.get("rows", "N/A"))
            index_ops = str(query.get("index_ops", 0))
            scan_ops = str(query.get("scan_ops", 0))
            click.echo(f"{name:<40} {time_ms:<12} {rows:<8} {index_ops:<8} {scan_ops:<8}")


def analyze_performance(optimizer: DatabaseOptimizer) -> None:
    """Analyze current database performance.

    Args:
        optimizer: Database optimizer instance
    """
    print_section("Analyzing Database Performance")

    # Get current index status
    click.echo("\n📊 Current Index Status:")
    current_indexes = optimizer.get_current_indexes()
    if current_indexes:
        for table, indexes in current_indexes.items():
            if indexes:
                click.echo(f"  Table: {table}")
                for idx in indexes:
                    click.echo(f"    ✓ {idx}")
    else:
        click.echo("  No custom indexes found")

    # Analyze table statistics
    click.echo("\n📈 Database Statistics:")
    stats = optimizer.analyze_table_statistics()
    if "detections" in stats:
        det_stats = stats["detections"]
        click.echo(f"  • Total detections: {det_stats.get('row_count', 0):,}")
        if "date_range" in det_stats:
            date_range = det_stats["date_range"]
            if date_range.get("min_date") and date_range.get("max_date"):
                click.echo(f"  • Date range: {date_range['min_date']} to {date_range['max_date']}")

    # Show what optimizations are available
    click.echo("\n💡 Available Optimizations:")
    click.echo("  • Create optimized indexes for common query patterns")
    click.echo("  • Analyze table statistics and update query planner")
    click.echo("  • Vacuum database to reclaim space")


def _display_created_indexes(created_indexes: list[str], dry_run: bool) -> None:
    """Display information about created indexes.

    Args:
        created_indexes: List of CREATE INDEX statements
        dry_run: Whether this is a dry run
    """
    if created_indexes:
        click.echo(
            f"  ✅ {'Would create' if dry_run else 'Created'} {len(created_indexes)} indexes:"
        )
        for idx in created_indexes[:5]:  # Show first 5
            # Extract index name from CREATE INDEX statement
            if "CREATE INDEX" in idx:
                parts = idx.split()
                if len(parts) >= 4:
                    idx_name = parts[3]
                    click.echo(f"     • {idx_name}")
        if len(created_indexes) > 5:
            click.echo(f"     ... and {len(created_indexes) - 5} more")
    else:
        click.echo("  ℹ️  No new indexes needed")  # noqa: RUF001


def _display_optimization_summary(created_indexes: list[str], result: dict[str, Any]) -> None:
    """Display optimization summary.

    Args:
        created_indexes: List of created indexes
        result: Optimization result dictionary
    """
    click.echo("\n📊 Optimization Summary:")
    if created_indexes:
        click.echo(f"  ✅ Created {len(created_indexes)} optimized indexes")
        click.echo("  🚀 Query performance should be significantly improved")
    if result.get("vacuum_result"):
        click.echo("  ✅ Database vacuumed successfully")
    if result.get("analyze_result"):
        click.echo("  ✅ Table statistics updated")

    if not created_indexes and not result.get("vacuum_result"):
        click.echo("  ℹ️  Database was already optimized")  # noqa: RUF001


def optimize_database(optimizer: DatabaseOptimizer, dry_run: bool = False) -> None:
    """Run database optimization.

    Args:
        optimizer: Database optimizer instance
        dry_run: If True, show what would be done without making changes
    """
    if dry_run:
        print_section("Optimization Plan (Dry Run)")
        click.echo("The following optimizations would be applied:")
    else:
        print_section("Running Database Optimization")

    # Create optimized indexes
    click.echo("\n🔧 Creating Optimized Indexes...")
    created_indexes = optimizer.create_optimized_indexes(dry_run=dry_run)
    _display_created_indexes(created_indexes, dry_run)

    if not dry_run:
        # Run full optimization
        click.echo("\n⚙️  Running Full Optimization...")
        result = optimizer.optimize_database()
        _display_optimization_summary(created_indexes, result)


def export_report(optimizer: DatabaseOptimizer, export_path: Path) -> None:
    """Export optimization report to JSON file.

    Args:
        optimizer: Database optimizer instance
        export_path: Path to export JSON file
    """
    print_section("Exporting Optimization Report")

    try:
        from datetime import datetime

        report = {
            "timestamp": datetime.now().isoformat(),
            "database_statistics": optimizer.analyze_table_statistics(),
            "existing_indexes": optimizer.get_current_indexes(),
            "optimization_available": {
                "create_indexes": True,
                "vacuum_database": True,
                "analyze_tables": True,
            },
        }

        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        click.echo(click.style(f"✅ Report exported to: {export_path}", fg="green"))

    except Exception as e:
        logger.error(f"Error exporting report: {e}")
        click.echo(click.style(f"❌ Export failed: {e}", fg="red"), err=True)


@click.command()
@click.option("--analyze", is_flag=True, help="Analyze current database performance")
@click.option("--optimize", is_flag=True, help="Run database optimization")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option(
    "--export", type=click.Path(path_type=Path), help="Export optimization report to JSON file"
)
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
def cli(
    analyze: bool, optimize: bool, dry_run: bool, export: Path | None, verbose: bool
) -> int | None:
    """Optimize BirdNET-Pi database for analytics queries.

    Examples:
      # Analyze current performance
      optimize-database --analyze

      # Run optimization (dry run)
      optimize-database --optimize --dry-run

      # Run full optimization
      optimize-database --optimize

      # Export optimization report
      optimize-database --export report.json

      # Full analysis and optimization
      optimize-database --analyze --optimize
    """
    # Set logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Require at least one action
    if not any([analyze, optimize, export]):
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        sys.exit(1)

    try:
        # Set up database service
        db_service = setup_database_service()
        optimizer = DatabaseOptimizer(db_service)

        print_section("BirdNET-Pi Database Optimizer", "Optimizing database for analytics queries")

        # Run requested actions
        if analyze:
            analyze_performance(optimizer)

        if optimize:
            optimize_database(optimizer, dry_run=dry_run)

        if export:
            export_report(optimizer, export)

        click.echo("\n✨ Done!")
        return 0

    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        click.echo(click.style(f"\n❌ Error: {e}", fg="red"), err=True)
        return 1


def main() -> None:
    """Entry point for the database optimizer CLI."""
    sys.exit(cli())


if __name__ == "__main__":
    main()
