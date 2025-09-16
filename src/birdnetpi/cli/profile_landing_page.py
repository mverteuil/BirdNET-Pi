"""CLI command to profile landing page performance."""

import asyncio
import logging
import tempfile
import webbrowser
from pathlib import Path

import click
from pyinstrument import Profiler

from birdnetpi.analytics.analytics import AnalyticsManager
from birdnetpi.analytics.presentation import PresentationManager
from birdnetpi.config import ConfigManager
from birdnetpi.database.core import CoreDatabaseService
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.system.path_resolver import PathResolver


async def profile_landing_page(
    verbose: bool = False,
    parallel: bool = False,
    component: str | None = None,
    html_output: bool = False,
    open_browser: bool = False,
) -> None:
    """Profile the landing page data fetching performance.

    Args:
        verbose: Show detailed timing for each operation
        parallel: Use parallel data fetching (experimental)
        component: Profile only a specific component (e.g., 'metrics', 'detection_log')
        html_output: Generate HTML output instead of text
        open_browser: Open HTML output in browser (requires html_output)
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

    # Set up pyinstrument profiler
    profiler = Profiler(async_mode="enabled")

    try:
        logger.info("Starting performance profiling...")
        click.echo("\n" + "=" * 60)
        click.echo("LANDING PAGE PERFORMANCE PROFILE")
        click.echo("=" * 60)

        # Start profiling
        profiler.start()

        # Profile specific component or full page
        if component:
            logger.info(f"Profiling component: {component}")
            data = await profile_component(
                presentation_manager,
                analytics_manager,
                detection_query_service,
                component,
            )
        else:
            # Profile the complete landing page data fetch
            data = await presentation_manager.get_landing_page_data()

            # Display results summary
            click.echo("\n✓ Successfully fetched landing page data")
            click.echo(f"  • Metrics: {len(vars(data.metrics))} fields")
            click.echo(f"  • Detection log: {len(data.detection_log)} entries")
            click.echo(f"  • Species frequency: {len(data.species_frequency)} species")
            click.echo(f"  • Hourly distribution: {len(data.hourly_distribution)} hours")
            click.echo(f"  • Visualization data: {len(data.visualization_data)} points")

        # Stop profiling
        profiler.stop()

        # Generate and display output
        if html_output:
            # Generate HTML output
            output = profiler.output_html()

            if open_browser:
                # Save to temp file and open in browser
                with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                    f.write(output)
                    temp_path = f.name

                click.echo(f"\n✓ Opening profile in browser: {temp_path}")
                webbrowser.open(f"file://{temp_path}")
            else:
                # Save to file in current directory
                output_file = Path("landing_page_profile.html")
                output_file.write_text(output)
                click.echo(f"\n✓ Profile saved to: {output_file}")
                click.echo("  Open in browser to view interactive flame graph")
        else:
            # Generate text output
            output = profiler.output_text(unicode=True, show_all=verbose)

            # Display timing report
            click.echo("\n" + "-" * 60)
            click.echo("PERFORMANCE REPORT")
            click.echo("-" * 60)
            click.echo(output)

            # Extract total time from profiler session
            session = profiler.last_session
            if session:
                total_time = session.duration

                # Performance analysis
                click.echo("\n" + "-" * 60)
                click.echo("PERFORMANCE ANALYSIS")
                click.echo("-" * 60)
                click.echo(f"\n🕐 Total Time: {total_time:.3f} seconds")

                if total_time < 0.5:
                    click.secho("✅ Excellent: Page loads in under 500ms", fg="green")
                elif total_time < 1.0:
                    click.secho("✅ Good: Page loads in under 1 second", fg="green")
                elif total_time < 2.0:
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
) -> dict | list | None:
    """Profile a specific component of the landing page.

    Args:
        presentation_manager: The presentation manager instance
        analytics_manager: The analytics manager instance
        detection_query_service: The detection query service instance
        component: Name of the component to profile

    Returns:
        The result from the component function
    """
    component_map = {
        "metrics": analytics_manager.get_dashboard_summary,
        "species_frequency": analytics_manager.get_species_frequency_analysis,
        "temporal_patterns": analytics_manager.get_temporal_patterns,
        "detection_log": lambda: detection_query_service.query_detections(limit=10),
        "scatter_data": analytics_manager.get_detection_scatter_data,
    }

    if component not in component_map:
        click.secho(f"❌ Unknown component: {component}", fg="red")
        click.echo(f"Available components: {', '.join(component_map.keys())}")
        return None

    # Execute the component function
    if asyncio.iscoroutinefunction(component_map[component]):
        result = await component_map[component]()
    else:
        result = component_map[component]()

    click.echo(f"\n✓ Successfully profiled component: {component}")
    if isinstance(result, dict):
        click.echo(f"  Result keys: {', '.join(result.keys())}")
    elif isinstance(result, list):
        click.echo(f"  Result items: {len(result)}")

    return result


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
@click.option("--html", is_flag=True, help="Generate HTML output with interactive flame graph")
@click.option("--browser", is_flag=True, help="Open HTML output in browser (requires --html)")
def main(verbose: bool, parallel: bool, component: str | None, html: bool, browser: bool) -> None:
    """Profile the landing page performance to identify bottlenecks.

    This command uses pyinstrument to measure the time taken to fetch and format
    all data required for the BirdNET-Pi landing page, helping identify performance
    bottlenecks in the data pipeline.

    Examples:
        # Basic text profiling
        profile-landing-page

        # Generate interactive HTML flame graph
        profile-landing-page --html

        # Open flame graph in browser
        profile-landing-page --html --browser

        # Verbose output with detailed call stack
        profile-landing-page --verbose

        # Test parallel data fetching
        profile-landing-page --parallel

        # Profile only the metrics component
        profile-landing-page --component metrics

        # Combine options
        profile-landing-page -v --html --browser -c species_frequency
    """
    if browser and not html:
        click.secho("⚠️  --browser requires --html", fg="yellow")
        html = True

    asyncio.run(profile_landing_page(verbose, parallel, component, html, browser))


if __name__ == "__main__":
    main()
