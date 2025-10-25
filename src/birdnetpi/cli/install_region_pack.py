"""CLI wrapper for installing eBird region packs.

This script provides command-line access to download and install
eBird region packs based on coordinates or region ID.
"""

import gzip
import shutil
import sys
from pathlib import Path
from urllib.request import urlopen

import click

from birdnetpi.config.manager import ConfigManager
from birdnetpi.releases.registry_service import RegionPackInfo, RegistryService
from birdnetpi.system.path_resolver import PathResolver


def _download_and_extract_pack(download_url: str, output_path: Path) -> None:
    """Download and extract a .db.gz file.

    Args:
        download_url: GitHub release asset download URL
        output_path: Path where the .db file should be saved

    Raises:
        Exception: If download or extraction fails
    """
    click.echo(f"  Downloading from: {download_url}")

    # Download the .db.gz file
    with urlopen(download_url, timeout=300) as response:  # nosemgrep
        total_size = int(response.headers.get("Content-Length", 0))
        chunk_size = 8192
        downloaded = 0

        # Create a temporary file for the compressed download
        temp_gz = output_path.with_suffix(".db.gz")

        with open(temp_gz, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break

                f.write(chunk)
                downloaded += len(chunk)

                # Show progress
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    click.echo(
                        f"\r  Progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)",
                        nl=False,
                    )

        click.echo()  # New line after progress

    # Extract the .db.gz file to .db
    click.echo("  Extracting...")
    with gzip.open(temp_gz, "rb") as f_in:
        with open(output_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    # Remove the temporary .gz file
    temp_gz.unlink()

    file_size = output_path.stat().st_size / 1024 / 1024
    click.echo(click.style(f"  ✓ Extraction complete ({file_size:.1f} MB)", fg="green"))


def _find_region_pack(
    registry_service: RegistryService,
    region_id: str | None,
    lat: float | None,
    lon: float | None,
) -> RegionPackInfo:
    """Find region pack by ID or coordinates.

    Returns:
        Region pack info or exits with error

    Raises:
        SystemExit: If pack not found or invalid parameters
    """
    if region_id:
        # Look up specific region in registry
        click.echo(f"Looking up region: {region_id}")
        registry = registry_service.fetch_registry()
        region_pack = next((r for r in registry.regions if r.region_id == region_id), None)

        if not region_pack:
            click.echo(
                click.style(f"✗ Error: Region '{region_id}' not found in registry", fg="red"),
                err=True,
            )
            sys.exit(1)

        return region_pack

    if lat is not None and lon is not None:
        # Find pack by coordinates
        click.echo(f"Finding region pack for coordinates: {lat}, {lon}")
        region_pack = registry_service.find_pack_for_coordinates(lat, lon)

        if not region_pack:
            click.echo(
                click.style(
                    f"✗ Error: No region pack found for coordinates ({lat}, {lon})",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

        click.echo(click.style(f"✓ Found region: {region_pack.region_id}", fg="green"))
        return region_pack

    click.echo(
        click.style(
            "✗ Error: Must provide --lat/--lon, --region-id, or --use-config",
            fg="red",
        ),
        err=True,
    )
    sys.exit(1)


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """EBird Region Pack Installer.

    Download and manage eBird species region packs for BirdNET-Pi.
    """
    ctx.ensure_object(dict)
    ctx.obj["path_resolver"] = PathResolver()
    ctx.obj["registry_service"] = RegistryService(ctx.obj["path_resolver"])


@cli.command()
@click.option(
    "--lat",
    type=float,
    help="Latitude for location-based pack selection",
)
@click.option(
    "--lon",
    type=float,
    help="Longitude for location-based pack selection",
)
@click.option(
    "--region-id",
    help="Specific region ID to install (e.g., 'north-america-northern-new-england')",
)
@click.option(
    "--use-config",
    is_flag=True,
    help="Use latitude/longitude from BirdNET configuration",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing pack if already installed",
)
@click.pass_context
def install(
    ctx: click.Context,
    lat: float | None,
    lon: float | None,
    region_id: str | None,
    use_config: bool,
    force: bool,
) -> None:
    """Install an eBird region pack.

    Examples:
      # Install pack for specific coordinates
      install-region-pack install --lat 43.0 --lon -71.5

      # Install pack using coordinates from config
      install-region-pack install --use-config

      # Install specific region by ID
      install-region-pack install --region-id north-america-northern-new-england

      # Force reinstall even if already present
      install-region-pack install --use-config --force
    """
    path_resolver = ctx.obj["path_resolver"]
    registry_service = ctx.obj["registry_service"]

    # Determine coordinates or region ID
    if use_config:
        # Load coordinates from config
        config_manager = ConfigManager(path_resolver)
        config = config_manager.load()
        lat = config.latitude
        lon = config.longitude

        if lat == 0.0 and lon == 0.0:
            click.echo(
                click.style(
                    "✗ Error: Location not configured. "
                    "Set coordinates in config or use --lat/--lon.",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

        click.echo(f"Using coordinates from config: {lat}, {lon}")

    # Find the appropriate pack using helper function
    region_pack = _find_region_pack(registry_service, region_id, lat, lon)

    if not region_pack.download_url:
        click.echo(
            click.style(
                f"✗ Error: Region '{region_pack.region_id}' has no download URL",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    # Check if already installed
    db_dir = path_resolver.data_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    output_path = db_dir / f"{region_pack.region_id}.db"

    if output_path.exists() and not force:
        click.echo(
            click.style(
                f"✓ Region pack '{region_pack.region_id}' already installed",
                fg="green",
            )
        )
        click.echo(f"  Location: {output_path}")
        click.echo("  Use --force to reinstall")
        sys.exit(0)

    # Download and install
    click.echo()
    click.echo(f"Installing region pack: {region_pack.region_id}")
    click.echo(f"  Size: {region_pack.total_size_mb:.1f} MB")
    click.echo(f"  Packs: {region_pack.pack_count} H3 cells")

    try:
        _download_and_extract_pack(region_pack.download_url, output_path)

        click.echo()
        click.echo(
            click.style(
                f"✓ Region pack '{region_pack.region_id}' installed successfully!",
                fg="green",
                bold=True,
            )
        )
        click.echo(f"  Location: {output_path}")

    except Exception as e:
        click.echo(
            click.style(f"✗ Error installing region pack: {e}", fg="red", bold=True),
            err=True,
        )
        # Clean up partial download
        if output_path.exists():
            output_path.unlink()
        if output_path.with_suffix(".db.gz").exists():
            output_path.with_suffix(".db.gz").unlink()
        sys.exit(1)


@cli.command("list")
@click.option(
    "--show-urls",
    is_flag=True,
    help="Show download URLs for each region",
)
@click.pass_context
def list_packs(ctx: click.Context, show_urls: bool) -> None:
    """List all available region packs from the registry."""
    registry_service = ctx.obj["registry_service"]

    try:
        click.echo("Fetching region pack registry...")
        registry = registry_service.fetch_registry()

        click.echo()
        click.echo(click.style("Available Region Packs:", bold=True))
        click.echo(f"  Registry version: {registry.version}")
        click.echo(f"  Total regions: {registry.total_regions}")
        click.echo(f"  Total packs: {registry.total_packs}")
        click.echo()

        for region in sorted(registry.regions, key=lambda r: r.region_id):
            click.echo(click.style(f"  • {region.region_id}", fg="cyan", bold=True))
            click.echo(f"    Size: {region.total_size_mb:.1f} MB")
            click.echo(f"    Packs: {region.pack_count} H3 cells")
            click.echo(f"    Center: {region.center['lat']:.2f}, {region.center['lon']:.2f}")

            if show_urls and region.download_url:
                click.echo(f"    URL: {region.download_url}")

            click.echo()

    except Exception as e:
        click.echo(
            click.style(f"✗ Error fetching registry: {e}", fg="red", bold=True),
            err=True,
        )
        sys.exit(1)


@cli.command("check-local")
@click.pass_context
def check_local(ctx: click.Context) -> None:
    """Check status of locally installed region packs."""
    path_resolver = ctx.obj["path_resolver"]

    db_dir = path_resolver.data_dir / "database"

    if not db_dir.exists():
        click.echo("No database directory found")
        sys.exit(0)

    click.echo("Local region pack status:")
    click.echo()

    # Find all .db files that look like region packs
    region_packs = []
    for db_file in db_dir.glob("*.db"):
        # Skip main databases
        if db_file.name in [
            "birdnetpi.db",
            "ioc_reference.db",
            "avibase_database.db",
            "patlevin_database.db",
        ]:
            continue

        # Region packs should match pattern: region-name-YYYY.MM.db
        region_packs.append(db_file)

    if not region_packs:
        click.echo("  No region packs installed")
        sys.exit(0)

    for pack in sorted(region_packs):
        file_size = pack.stat().st_size / 1024 / 1024
        click.echo(click.style(f"  ✓ {pack.stem}", fg="green"))
        click.echo(f"    Location: {pack}")
        click.echo(f"    Size: {file_size:.1f} MB")
        click.echo()


@cli.command("find")
@click.option(
    "--lat",
    type=float,
    required=True,
    help="Latitude",
)
@click.option(
    "--lon",
    type=float,
    required=True,
    help="Longitude",
)
@click.pass_context
def find_pack(ctx: click.Context, lat: float, lon: float) -> None:
    """Find the appropriate region pack for given coordinates.

    Examples:
      # Find pack for Boston, MA
      install-region-pack find --lat 42.36 --lon -71.06

      # Find pack for Hawaii
      install-region-pack find --lat 21.3 --lon -157.8
    """
    registry_service = ctx.obj["registry_service"]

    try:
        click.echo(f"Finding region pack for coordinates: {lat}, {lon}")
        region_pack = registry_service.find_pack_for_coordinates(lat, lon)

        if not region_pack:
            click.echo(
                click.style(
                    f"No region pack found for coordinates ({lat}, {lon})",
                    fg="yellow",
                )
            )
            sys.exit(0)

        click.echo()
        click.echo(click.style("✓ Found region pack:", fg="green", bold=True))
        click.echo(f"  Region ID: {region_pack.region_id}")
        click.echo(f"  Size: {region_pack.total_size_mb:.1f} MB")
        click.echo(f"  Packs: {region_pack.pack_count} H3 cells")
        click.echo(f"  Center: {region_pack.center['lat']:.2f}, {region_pack.center['lon']:.2f}")
        click.echo()
        click.echo("To install this pack, run:")
        click.echo(f"  install-region-pack install --region-id {region_pack.region_id}")

    except Exception as e:
        click.echo(
            click.style(f"✗ Error finding region pack: {e}", fg="red", bold=True),
            err=True,
        )
        sys.exit(1)


def main() -> None:
    """Entry point for the region pack installer CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
