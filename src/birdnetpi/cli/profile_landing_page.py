"""CLI command to profile landing page performance."""

import asyncio
import logging

import click

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.utils.profiling import PerformanceProfiler


async def profile_landing_page(
    verbose: bool = False,
    parallel: bool = False,
    component: str | None = None,
) -> None:
    """Profile the landing page data fetching performance.

    Args:
        verbose: Show detailed timing for each operation
        parallel: Use parallel data fetching (experimental)
        component: Profile only a specific component (e.g., 'metrics', 'detection_log')
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Initialize components
    path_resolver = PathResolver()
    config_manager = ConfigManager(path_resolver)
    config = config_manager.load()

    # Initialize database services
    logger.info("Initializing database services...")
    core_database = CoreDatabaseService(path_resolver.get_database_path())
    await core_database.initialize()

    species_database = SpeciesDatabaseService(path_resolver)

    # Initialize query and analytics services
    detection_query_service = DetectionQueryService(core_database, species_database)
    analytics_manager = AnalyticsManager(detection_query_service, config)

    # Create presentation manager
    presentation_manager = PresentationManager(analytics_manager, detection_query_service, config)

    if parallel:
        logger.info("Note: Parallel mode is experimental and may not show improvements yet")

    # Set up profiler
    profiler = PerformanceProfiler("Landing Page Performance")

    try:
        logger.info("Starting performance profiling...")
        click.echo("\n" + "=" * 60)
        click.echo("LANDING PAGE PERFORMANCE PROFILE")
        click.echo("=" * 60)

        # Profile specific component or full page
        if component:
            logger.info(f"Profiling component: {component}")
            await profile_component(
                presentation_manager,
                analytics_manager,
                detection_query_service,
                component,
                profiler,
            )
        else:
            # Profile the complete landing page data fetch
            async with profiler.aprofile("total_landing_page"):
                data = await presentation_manager.get_landing_page_data()

            # Display results summary
            click.echo("\n✓ Successfully fetched landing page data")
            click.echo(f"  • Metrics: {len(vars(data.metrics))} fields")
            click.echo(f"  • Detection log: {len(data.detection_log)} entries")
            click.echo(f"  • Species frequency: {len(data.species_frequency)} species")
            click.echo(f"  • Hourly distribution: {len(data.hourly_distribution)} hours")
            click.echo(f"  • Visualization data: {len(data.visualization_data)} points")

        # Display timing report
        click.echo("\n" + "-" * 60)
        click.echo("PERFORMANCE REPORT")
        click.echo("-" * 60)
        report = profiler.get_report()

        # Display total time prominently
        click.echo(f"\n🕐 Total Time: {report['total_time']:.3f} seconds")

        if report["operations"]:
            click.echo("\nOperation Breakdown:")
            # Sort by total time descending
            sorted_ops = sorted(
                report["operations"].items(), key=lambda x: x[1]["total"], reverse=True
            )

            for operation, stats in sorted_ops:
                click.echo(f"  • {operation}:")
                click.echo(f"    - Total: {stats['total']:.3f}s")
                if stats["count"] > 1:
                    click.echo(f"    - Count: {stats['count']}")
                    click.echo(f"    - Average: {stats['average']:.3f}s")
                    click.echo(f"    - Min/Max: {stats['min']:.3f}s / {stats['max']:.3f}s")

        # Performance analysis
        click.echo("\n" + "-" * 60)
        click.echo("PERFORMANCE ANALYSIS")
        click.echo("-" * 60)

        if report["total_time"] < 0.5:
            click.secho("✅ Excellent: Page loads in under 500ms", fg="green")
        elif report["total_time"] < 1.0:
            click.secho("✅ Good: Page loads in under 1 second", fg="green")
        elif report["total_time"] < 2.0:
            click.secho("⚠️  Warning: Page takes 1-2 seconds to load", fg="yellow")
        else:
            click.secho("❌ Critical: Page takes over 2 seconds to load", fg="red")
            click.echo("\nConsider:")
            click.echo("  • Enabling caching for expensive queries")
            click.echo("  • Using parallel data fetching (--parallel)")
            click.echo("  • Optimizing database queries")
            click.echo("  • Reducing the amount of data fetched")

    finally:
        # Clean up
        await core_database.dispose()
        # Species database doesn't have dispose method


async def profile_component(
    presentation_manager: PresentationManager,
    analytics_manager: AnalyticsManager,
    detection_query_service: DetectionQueryService,
    component: str,
    profiler: PerformanceProfiler,
) -> None:
    """Profile a specific component of the landing page.

    Args:
        presentation_manager: The presentation manager instance
        analytics_manager: The analytics manager instance
        detection_query_service: The detection query service instance
        component: Name of the component to profile
        profiler: Performance profiler instance
    """
    component_map = {
        "metrics": analytics_manager.get_dashboard_summary,
        "species_frequency": analytics_manager.get_species_frequency_analysis,
        "temporal_patterns": analytics_manager.get_temporal_patterns,
        "detection_log": lambda: detection_query_service.query_detections(limit=10),
        "scatter_data": analytics_manager.get_detection_scatter_data,
        "system_status": lambda: presentation_manager._get_system_status(),
    }

    if component not in component_map:
        click.secho(f"❌ Unknown component: {component}", fg="red")
        click.echo(f"Available components: {', '.join(component_map.keys())}")
        return

    async with profiler.aprofile(f"component_{component}"):
        if asyncio.iscoroutinefunction(component_map[component]):
            result = await component_map[component]()
        else:
            result = component_map[component]()

    click.echo(f"\n✓ Successfully profiled component: {component}")
    if isinstance(result, dict):
        click.echo(f"  Result keys: {', '.join(result.keys())}")
    elif isinstance(result, list):
        click.echo(f"  Result items: {len(result)}")


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed timing for each operation")
@click.option("--parallel", "-p", is_flag=True, help="Use parallel data fetching (experimental)")
@click.option(
    "--component",
    "-c",
    type=click.Choice(
        [
            "metrics",
            "species_frequency",
            "temporal_patterns",
            "detection_log",
            "scatter_data",
            "system_status",
        ]
    ),
    help="Profile only a specific component",
)
def main(verbose: bool, parallel: bool, component: str | None) -> None:
    """Profile the landing page performance to identify bottlenecks.

    This command measures the time taken to fetch and format all data
    required for the BirdNET-Pi landing page, helping identify performance
    bottlenecks in the data pipeline.

    Examples:
        # Basic profiling
        profile-landing-page

        # Verbose output with detailed timings
        profile-landing-page --verbose

        # Test parallel data fetching
        profile-landing-page --parallel

        # Profile only the metrics component
        profile-landing-page --component metrics

        # Combine options
        profile-landing-page -v -p -c species_frequency
    """
    asyncio.run(profile_landing_page(verbose, parallel, component))


if __name__ == "__main__":
    main()
