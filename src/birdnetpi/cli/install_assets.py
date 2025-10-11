"""CLI wrapper for installing BirdNET-Pi assets from releases.

This script provides command-line access to download and install
complete asset releases including models and databases for local
development and CI environments.
"""

import json
import sys
from pathlib import Path

import click

from birdnetpi.releases.asset_manifest import AssetManifest
from birdnetpi.releases.update_manager import UpdateManager
from birdnetpi.system.path_resolver import PathResolver


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """BirdNET-Pi Asset Installer.

    Download and manage BirdNET-Pi assets including models and databases.
    """
    ctx.ensure_object(dict)
    ctx.obj["path_resolver"] = PathResolver()
    ctx.obj["update_manager"] = UpdateManager(ctx.obj["path_resolver"])


def _check_existing_assets(
    path_resolver: PathResolver, requested_version: str
) -> tuple[bool, list[str]]:
    """Check if all required assets exist and are the correct version.

    Returns:
        Tuple of (all_present, missing_assets)
    """
    # First check version file
    version_file = path_resolver.data_dir / ".birdnet-assets-version"

    if version_file.exists():
        try:
            installed_version = version_file.read_text().strip()
            if installed_version != requested_version:
                msg = f"Version mismatch: installed={installed_version}, "
                msg += f"requested={requested_version}"
                click.echo(click.style(msg, fg="yellow"))
                return False, ["Version mismatch - need to update"]
        except Exception:
            # If we can't read version, assume mismatch
            return False, ["Cannot read version file"]
    else:
        # No version file means we need to install
        return False, ["No version file - need to install"]
    required_checks = []

    for asset in AssetManifest.get_required_assets():
        method = getattr(path_resolver, asset.path_method)
        asset_path = method()

        # For models directory, check for model and label files
        if asset.is_directory:
            # Check if directory exists and has model files (.tflite) or label files (.txt)
            if asset_path.exists():
                model_files = list(asset_path.glob("*.tflite"))
                label_files = list(asset_path.glob("*.txt"))
                if model_files or label_files:
                    check_path = asset_path  # Directory exists with model assets
                else:
                    check_path = asset_path / "dummy"  # Will fail the check
            else:
                check_path = asset_path
        else:
            check_path = asset_path

        required_checks.append((check_path, asset.name))

    all_present = True
    missing_assets = []

    for path, name in required_checks:
        if not path.exists():
            all_present = False
            missing_assets.append(name)

    return all_present, missing_assets


def _perform_installation(update_manager: "UpdateManager", version: str) -> dict:
    """Perform the actual asset installation.

    Returns:
        Installation result dictionary
    """
    # Always download all assets for consistency
    return update_manager.download_release_assets(
        version=version,
        include_models=True,
        include_ioc_db=True,
        include_wikidata_db=True,
        github_repo="mverteuil/BirdNET-Pi",
    )


def _display_installation_results(result: dict, output_json: str | None) -> None:
    """Display installation results and optionally save to JSON."""
    click.echo()
    click.echo(click.style("✓ Asset installation completed successfully!", fg="green", bold=True))
    click.echo(f"  Version: {result['version']}")
    click.echo(f"  Downloaded assets: {len(result['downloaded_assets'])}")

    for asset in result["downloaded_assets"]:
        click.echo(f"    • {asset}")

    # Output JSON if requested
    if output_json:
        Path(output_json).write_text(json.dumps(result, indent=2))
        click.echo()
        click.echo(f"Installation data written to: {output_json}")


@cli.command()
@click.argument("version")
@click.option(
    "--skip-existing",
    is_flag=True,
    help="Skip download if assets already exist (ideal for init containers)",
)
@click.option("--output-json", help="Output installation data to JSON file")
@click.option("--remote", default="origin", help="Git remote to fetch from")
@click.pass_context
def install(
    ctx: click.Context, version: str, skip_existing: bool, output_json: str | None, remote: str
) -> None:
    """Install complete asset release or verify installation.

    VERSION: Release version to install (e.g., 'v2.0.0' or 'latest')

    Examples:
      # Install latest release
      install-assets install latest

      # Install specific version
      install-assets install v2.1.1

      # Skip if assets already exist (for init containers)
      install-assets install v2.1.1 --skip-existing

      # Save installation info to JSON
      install-assets install latest --output-json install.json
    """
    path_resolver = ctx.obj["path_resolver"]

    if skip_existing:
        # Skip existing mode - check if all required assets exist, install only if missing
        all_present, missing_assets = _check_existing_assets(path_resolver, version)

        if all_present:
            click.echo(click.style(f"✓ All assets present for version {version}", fg="green"))
            sys.exit(0)
        else:
            click.echo(click.style(f"✗ Missing assets: {', '.join(missing_assets)}", fg="yellow"))
            click.echo(f"Installing missing assets for version: {version}")
            # Continue to installation below

    update_manager = ctx.obj["update_manager"]
    click.echo(f"Installing complete asset release: {version}")

    try:
        result = _perform_installation(update_manager, version)

        # Write version file after successful installation
        version_file = path_resolver.data_dir / ".birdnet-assets-version"
        try:
            version_file.write_text(version)
            click.echo(f"  Version marker written: {version}")
        except Exception as e:
            click.echo(
                click.style(f"Warning: Could not write version file: {e}", fg="yellow"), err=True
            )

        _display_installation_results(result, output_json)

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
            click.echo("│    uv run install-assets install v2.1.1" + " " * 37 + "│")
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

    # Use AssetManifest to check all assets
    for asset in AssetManifest.get_all_assets():
        method = getattr(path_resolver, asset.path_method)
        asset_path = method()

        if asset.is_directory:
            # For directories (models), check if they exist and have content
            if asset_path.exists():
                model_files = list(asset_path.rglob("*.tflite"))
                label_files = list(asset_path.rglob("*.txt"))
                total_size = sum(f.stat().st_size for f in asset_path.rglob("*") if f.is_file())
                size_mb = total_size / 1024 / 1024

                file_count_str = ""
                if model_files:
                    file_count_str += f"{len(model_files)} models"
                if label_files:
                    if file_count_str:
                        file_count_str += f", {len(label_files)} labels"
                    else:
                        file_count_str = f"{len(label_files)} labels"

                click.echo(
                    click.style(
                        f"  ✓ {asset.name}: {file_count_str} ({size_mb:.1f} MB)",
                        fg="green",
                    )
                )
                click.echo(f"    Location: {asset_path}")

                if verbose:
                    all_files = sorted(model_files + label_files)
                    for asset_file in all_files:
                        file_size = asset_file.stat().st_size / 1024 / 1024
                        file_type = "model" if asset_file.suffix == ".tflite" else "labels"
                        click.echo(f"      - {asset_file.name} ({file_size:.1f} MB) [{file_type}]")
            else:
                click.echo(click.style(f"  ✗ {asset.name}: Not installed", fg="red"))
                click.echo(f"    Expected location: {asset_path}")
        else:
            # For files (databases), check if they exist
            if asset_path.exists():
                file_size = asset_path.stat().st_size / 1024 / 1024
                click.echo(click.style(f"  ✓ {asset.name}: {file_size:.1f} MB", fg="green"))
                click.echo(f"    Location: {asset_path}")
            else:
                click.echo(click.style(f"  ✗ {asset.name}: Not installed", fg="red"))
                click.echo(f"    Expected location: {asset_path}")

    click.echo()


def main() -> None:
    """Entry point for the asset installer CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
