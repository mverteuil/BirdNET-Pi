"""CLI wrapper for installing BirdNET-Pi assets from releases.

This script provides command-line access to download and install
complete asset releases including models and databases for local
development and CI environments.
"""

import json
import sys
from pathlib import Path

import click

from birdnetpi.managers.update_manager import UpdateManager
from birdnetpi.utils.path_resolver import PathResolver


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """BirdNET-Pi Asset Installer.

    Download and manage BirdNET-Pi assets including models and databases.
    """
    ctx.ensure_object(dict)
    ctx.obj["path_resolver"] = PathResolver()
    ctx.obj["update_manager"] = UpdateManager(ctx.obj["path_resolver"])


@cli.command()
@click.argument("version")
@click.option("--output-json", help="Output installation data to JSON file")
@click.option("--remote", default="origin", help="Git remote to fetch from")
@click.pass_context
def install(ctx: click.Context, version: str, output_json: str | None, remote: str) -> None:
    """Install complete asset release.

    VERSION: Release version to install (e.g., 'v2.0.0' or 'latest')

    Examples:
      # Install latest release
      asset-installer install latest

      # Install specific version
      asset-installer install v2.1.0

      # Save installation info to JSON
      asset-installer install latest --output-json install.json
    """
    update_manager = ctx.obj["update_manager"]

    click.echo(f"Installing complete asset release: {version}")

    try:
        # Always download all assets for consistency
        result = update_manager.download_release_assets(
            version=version,
            include_models=True,
            include_ioc_db=True,
            include_avibase_db=True,
            include_patlevin_db=True,
            github_repo="mverteuil/BirdNET-Pi",
        )

        click.echo()
        click.echo(
            click.style("✓ Asset installation completed successfully!", fg="green", bold=True)
        )
        click.echo(f"  Version: {result['version']}")
        click.echo(f"  Downloaded assets: {len(result['downloaded_assets'])}")

        for asset in result["downloaded_assets"]:
            click.echo(f"    • {asset}")

        # Output JSON if requested
        if output_json:
            Path(output_json).write_text(json.dumps(result, indent=2))
            click.echo()
            click.echo(f"Installation data written to: {output_json}")

    except Exception as e:
        error_msg = str(e)
        click.echo(
            click.style(f"✗ Error installing assets: {error_msg}", fg="red", bold=True), err=True
        )

        # Show helpful local development message for permission errors
        if "Permission denied" in error_msg and "/var/lib/birdnetpi" in error_msg:
            click.echo()
            click.echo("┌" + "─" * 78 + "┐")
            click.echo("│" + " " * 78 + "│")
            click.echo("│  🛠️  LOCAL DEVELOPMENT SETUP REQUIRED" + " " * 39 + "│")
            click.echo("│" + " " * 78 + "│")
            click.echo(
                "│  For local development, you need to set the BIRDNETPI_DATA environment"
                + " " * 5
                + "│"
            )
            click.echo(
                "│  variable to a writable directory (e.g., ./data in your project root)."
                + " " * 4
                + "│"
            )
            click.echo("│" + " " * 78 + "│")
            click.echo("│  Run the asset installer with:" + " " * 44 + "│")
            click.echo("│    export BIRDNETPI_DATA=./data" + " " * 43 + "│")
            click.echo("│    uv run asset-installer install v2.1.0" + " " * 34 + "│")
            click.echo("│" + " " * 78 + "│")
            click.echo(
                "│  Or set it permanently in your shell profile (e.g., ~/.bashrc):" + " " * 12 + "│"
            )
            click.echo("│    echo 'export BIRDNETPI_DATA=./data' >> ~/.bashrc" + " " * 24 + "│")
            click.echo("│" + " " * 78 + "│")
            click.echo("└" + "─" * 78 + "┘")
            click.echo()

        sys.exit(1)


@cli.command("list-versions")
@click.option("--remote", default="origin", help="Git remote to check")
@click.pass_context
def list_versions(ctx: click.Context, remote: str) -> None:
    """List available asset versions."""
    update_manager = ctx.obj["update_manager"]

    try:
        versions = update_manager.list_available_versions(github_repo="mverteuil/BirdNET-Pi")

        click.echo("Available asset versions:")
        click.echo()

        if not versions:
            click.echo("  No asset versions found.")
            return

        click.echo(click.style(f"Latest version: {versions[0] if versions else 'None'}", bold=True))
        click.echo()

        for version in versions:
            click.echo(f"  • {version}")

    except Exception as e:
        click.echo(
            click.style(f"✗ Error listing available assets: {e}", fg="red", bold=True), err=True
        )
        sys.exit(1)


@cli.command("check-local")
@click.option("--verbose", is_flag=True, help="Show detailed file information")
@click.pass_context
def check_local(ctx: click.Context, verbose: bool) -> None:
    """Check status of locally installed assets."""
    path_resolver = ctx.obj["path_resolver"]

    click.echo("Local asset status:")
    click.echo()

    # Check models
    models_dir = Path(path_resolver.get_models_dir())
    if models_dir.exists():
        model_files = list(models_dir.rglob("*.tflite"))
        total_size = sum(f.stat().st_size for f in models_dir.rglob("*") if f.is_file())
        size_mb = total_size / 1024 / 1024

        click.echo(
            click.style(
                f"  ✓ Models: {len(model_files)} model files ({size_mb:.1f} MB)", fg="green"
            )
        )
        click.echo(f"    Location: {models_dir}")

        if verbose:
            for model_file in sorted(model_files):
                file_size = model_file.stat().st_size / 1024 / 1024
                click.echo(f"      - {model_file.name} ({file_size:.1f} MB)")
    else:
        click.echo(click.style("  ✗ Models: Not installed", fg="red"))
        click.echo(f"    Expected location: {models_dir}")

    click.echo()

    # Check IOC database
    ioc_db_path = Path(path_resolver.get_ioc_database_path())
    if ioc_db_path.exists():
        file_size = ioc_db_path.stat().st_size / 1024 / 1024
        click.echo(click.style(f"  ✓ IOC Database: {file_size:.1f} MB", fg="green"))
        click.echo(f"    Location: {ioc_db_path}")
    else:
        click.echo(click.style("  ✗ IOC Database: Not installed", fg="red"))
        click.echo(f"    Expected location: {ioc_db_path}")

    # Check Avibase database
    avibase_path = Path(path_resolver.get_data_dir()) / "avibase.db"
    if avibase_path.exists():
        file_size = avibase_path.stat().st_size / 1024 / 1024
        click.echo(click.style(f"  ✓ Avibase Database: {file_size:.1f} MB", fg="green"))
        click.echo(f"    Location: {avibase_path}")
    else:
        click.echo(click.style("  ✗ Avibase Database: Not installed", fg="red"))
        click.echo(f"    Expected location: {avibase_path}")

    # Check PatLevin database
    patlevin_path = Path(path_resolver.get_data_dir()) / "patlevin.db"
    if patlevin_path.exists():
        file_size = patlevin_path.stat().st_size / 1024 / 1024
        click.echo(click.style(f"  ✓ PatLevin Database: {file_size:.1f} MB", fg="green"))
        click.echo(f"    Location: {patlevin_path}")
    else:
        click.echo(click.style("  ✗ PatLevin Database: Not installed", fg="red"))
        click.echo(f"    Expected location: {patlevin_path}")

    click.echo()


def main() -> None:
    """Entry point for the asset installer CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
