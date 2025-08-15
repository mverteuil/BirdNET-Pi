#!/usr/bin/env python3
"""Command-line tool for optimizing the BirdNET-Pi database for analytics queries.

This script provides database optimization capabilities including:
- Creating optimized indexes for common query patterns
- Analyzing query performance
- Generating optimization recommendations
- Monitoring database health
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from birdnetpi.services.database_service import DatabaseService
from birdnetpi.utils.database_optimizer import DatabaseOptimizer
from birdnetpi.utils.file_path_resolver import FilePathResolver

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
    resolver = FilePathResolver()
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
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")
    if content:
        print(content)


def print_query_performance(performance_data: list, title: str) -> None:
    """Print query performance results in a formatted table.

    Args:
        performance_data: List of query performance dictionaries
        title: Table title
    """
    print_section(title)

    if not performance_data:
        print("No performance data available.")
        return

    # Print table header
    print(f"{'Query Name':<40} {'Time (ms)':<12} {'Rows':<8} {'Index':<8} {'Scan':<8}")
    print("-" * 80)

    # Print each query's performance
    for query in performance_data:
        if "error" in query:
            print(f"{query['name']:<40} Error: {query['error']}")
        else:
            name = query["name"][:39]
            time_ms = f"{query.get('execution_time_ms', 'N/A'):<12}"
            rows = f"{query.get('row_count', 'N/A'):<8}"
            uses_index = "Yes" if query.get("uses_index") else "No"
            full_scan = "Yes" if query.get("full_table_scan") else "No"

            print(f"{name:<40} {time_ms} {rows} {uses_index:<8} {full_scan:<8}")


def print_statistics(stats: dict) -> None:
    """Print database statistics.

    Args:
        stats: Statistics dictionary
    """
    print_section("Database Statistics")

    # Table information
    tables = stats.get("tables", {})
    for table_name, info in tables.items():
        if "error" in info:
            print(f"\n{table_name}: Error - {info['error']}")
        else:
            print(f"\n{table_name}:")
            print(f"  Rows: {info.get('row_count', 'N/A'):,}")
            print(f"  Columns: {info.get('columns', 'N/A')}")

    # Date range
    date_range = stats.get("date_range", {})
    if date_range:
        print("\nDate Range:")
        print(f"  Earliest: {date_range.get('earliest', 'N/A')}")
        print(f"  Latest: {date_range.get('latest', 'N/A')}")
        print(f"  Span: {date_range.get('days_span', 'N/A')} days")

    # Confidence distribution
    conf_dist = stats.get("confidence_distribution", {})
    if conf_dist:
        print("\nConfidence Distribution:")
        print(f"  Min: {conf_dist.get('min', 'N/A')}")
        print(f"  Max: {conf_dist.get('max', 'N/A')}")
        print(f"  Average: {conf_dist.get('average', 'N/A')}")
        print(f"  High confidence (>0.8): {conf_dist.get('high_confidence_count', 'N/A'):,}")

    # Top species
    top_species = stats.get("top_species", [])
    if top_species:
        print("\nTop 10 Species by Detection Count:")
        for i, species in enumerate(top_species[:10], 1):
            print(f"  {i:2}. {species['species']:<40} {species['count']:,} detections")


def analyze_performance(optimizer: DatabaseOptimizer) -> None:
    """Analyze current query performance.

    Args:
        optimizer: DatabaseOptimizer instance
    """
    print_section("Analyzing Query Performance")

    try:
        # Get current indexes
        indexes = optimizer.get_current_indexes()
        print("\nCurrent Indexes:")
        for table, idx_list in indexes.items():
            print(f"\n{table}:")
            if idx_list:
                for idx in idx_list:
                    print(f"  - {idx}")
            else:
                print("  No indexes found")

        # Analyze query performance
        print("\nAnalyzing common queries...")
        performance = optimizer.monitor.analyze_common_queries()
        print_query_performance(performance, "Current Query Performance")

        # Get statistics
        stats = optimizer.analyze_table_statistics()
        print_statistics(stats)

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        print(f"\nError: {e}")


def optimize_database(optimizer: DatabaseOptimizer, dry_run: bool = False) -> None:
    """Run database optimization.

    Args:
        optimizer: DatabaseOptimizer instance
        dry_run: If True, only show what would be done
    """
    if dry_run:
        print_section("Optimization Plan (Dry Run)")

        # Show indexes that would be created
        sql_statements = optimizer.create_optimized_indexes(dry_run=True)
        print("\nIndexes to be created:")
        for sql in sql_statements:
            # Extract index name from SQL
            if "CREATE INDEX" in sql:
                parts = sql.split()
                idx_name = parts[parts.index("INDEX") + 3] if "INDEX" in parts else "unknown"
                print(f"  - {idx_name}")

        print("\nDatabase would be VACUUMed after index creation.")
        print("\nRun without --dry-run to apply optimizations.")
    else:
        print_section("Running Database Optimization")
        print("This may take several minutes depending on database size...")

        try:
            results = optimizer.optimize_database()

            # Show created indexes
            if results.get("created_indexes"):
                print(f"\nCreated {len(results['created_indexes'])} indexes:")
                for sql in results["created_indexes"]:
                    if "CREATE INDEX" in sql:
                        parts = sql.split()
                        idx_name = (
                            parts[parts.index("INDEX") + 3] if "INDEX" in parts else "unknown"
                        )
                        print(f"  ✓ {idx_name}")

            # Show performance comparison
            if results.get("query_performance_before") and results.get("query_performance_after"):
                print_query_performance(
                    results["query_performance_before"], "Query Performance BEFORE Optimization"
                )
                print_query_performance(
                    results["query_performance_after"], "Query Performance AFTER Optimization"
                )

                # Calculate improvement
                before_times = [
                    q.get("execution_time_ms", 0)
                    for q in results["query_performance_before"]
                    if "execution_time_ms" in q
                ]
                after_times = [
                    q.get("execution_time_ms", 0)
                    for q in results["query_performance_after"]
                    if "execution_time_ms" in q
                ]

                if before_times and after_times:
                    avg_before = sum(before_times) / len(before_times)
                    avg_after = sum(after_times) / len(after_times)
                    improvement = ((avg_before - avg_after) / avg_before) * 100

                    print(f"\nAverage query time improvement: {improvement:.1f}%")
                    print(f"  Before: {avg_before:.2f}ms")
                    print(f"  After: {avg_after:.2f}ms")

            # Show recommendations
            if results.get("recommendations"):
                print_section("Optimization Recommendations")
                for i, rec in enumerate(results["recommendations"], 1):
                    print(f"{i}. {rec}")

            print_section("Optimization Complete", "✅ Database has been optimized successfully!")

        except Exception as e:
            logger.error(f"Error during optimization: {e}")
            print(f"\n❌ Optimization failed: {e}")


def export_report(optimizer: DatabaseOptimizer, output_path: Path) -> None:
    """Export optimization report to JSON file.

    Args:
        optimizer: DatabaseOptimizer instance
        output_path: Path to output file
    """
    print_section("Exporting Optimization Report")

    try:
        # Run full optimization analysis
        results = optimizer.optimize_database()

        # Write to file
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"✅ Report exported to: {output_path}")

        # Show summary
        if results.get("created_indexes"):
            print(f"  - Created {len(results['created_indexes'])} indexes")
        if results.get("recommendations"):
            print(f"  - Generated {len(results['recommendations'])} recommendations")

    except Exception as e:
        logger.error(f"Error exporting report: {e}")
        print(f"❌ Export failed: {e}")


def main() -> int:
    """Main entry point for the optimization script.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Optimize BirdNET-Pi database for analytics queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze current performance
  %(prog)s --analyze

  # Run optimization (dry run)
  %(prog)s --optimize --dry-run

  # Run full optimization
  %(prog)s --optimize

  # Export optimization report
  %(prog)s --export report.json

  # Full analysis and optimization
  %(prog)s --analyze --optimize
        """,
    )

    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze current database performance",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run database optimization",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--export",
        type=Path,
        metavar="PATH",
        help="Export optimization report to JSON file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Require at least one action
    if not any([args.analyze, args.optimize, args.export]):
        parser.print_help()
        return 1

    try:
        # Set up database service
        db_service = setup_database_service()
        optimizer = DatabaseOptimizer(db_service)

        print_section("BirdNET-Pi Database Optimizer", "Optimizing database for analytics queries")

        # Run requested actions
        if args.analyze:
            analyze_performance(optimizer)

        if args.optimize:
            optimize_database(optimizer, dry_run=args.dry_run)

        if args.export:
            export_report(optimizer, args.export)

        return 0

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
