"""CLI wrapper for release management operations.

This script provides command-line access to the ReleaseManager functionality
for creating automated releases with orphaned commit asset distribution.
"""

import json
import sys
from pathlib import Path
from typing import Any

import click

from birdnetpi.releases.release_manager import ReleaseAsset, ReleaseConfig, ReleaseManager
from birdnetpi.utils.path_resolver import PathResolver


def _add_asset_if_requested(
    include_flag: bool,
    filename_pattern: str,
    warning_msg: str,
    default_assets: list[ReleaseAsset],
    assets: list[ReleaseAsset],
) -> None:
    """Add asset if requested and found."""
    if not include_flag:
        return

    asset = next((a for a in default_assets if filename_pattern in str(a.target_name)), None)
    if asset and Path(asset.source_path).exists():
        assets.append(asset)
    else:
        click.echo(click.style(f"Warning: {warning_msg}", fg="yellow"), err=True)


def _build_asset_list(
    include_models: bool,
    include_ioc_db: bool,
    include_avibase_db: bool,
    include_patlevin_db: bool,
    custom_assets: tuple[str, ...],
    release_manager: ReleaseManager,
) -> list[ReleaseAsset]:
    """Build the list of assets for the release."""
    assets = []
    default_assets = release_manager.get_default_assets()

    # Map of arguments to their corresponding asset patterns and warnings
    asset_configs = [
        (include_models, "models", "Models not found at expected locations"),
        (include_ioc_db, "ioc_reference.db", "IOC database not found at expected locations"),
        (
            include_avibase_db,
            "avibase_database.db",
            "Avibase database not found at expected locations",
        ),
        (
            include_patlevin_db,
            "patlevin_database.db",
            "PatLevin database not found at expected locations",
        ),
    ]

    for include_flag, pattern, warning in asset_configs:
        _add_asset_if_requested(include_flag, pattern, warning, default_assets, assets)

    # Add custom assets
    if custom_assets:
        _add_custom_assets(custom_assets, assets)

    if not assets:
        click.echo(click.style("Error: No assets specified for release", fg="red"), err=True)
        sys.exit(1)

    return assets


def _add_custom_assets(custom_assets: tuple[str, ...], assets: list[ReleaseAsset]) -> None:
    """Add custom assets to the asset list."""
    for asset_spec in custom_assets:
        parts = asset_spec.split(":")
        if len(parts) != 3:
            click.echo(
                click.style(f"Error: Invalid asset specification: {asset_spec}", fg="red"),
                err=True,
            )
            click.echo("Format: source_path:target_name:description", err=True)
            sys.exit(1)

        source_path, target_name, description = parts
        if not Path(source_path).exists():
            click.echo(click.style(f"Error: Asset not found: {source_path}", fg="red"), err=True)
            sys.exit(1)

        assets.append(ReleaseAsset(Path(source_path), Path(target_name), description))


def _handle_github_release(
    create_github_release: bool,
    config: ReleaseConfig,
    release_manager: ReleaseManager,
    asset_result: dict,
) -> dict | None:
    """Create GitHub release if requested."""
    if not create_github_release:
        return None

    click.echo()
    click.echo("Creating GitHub release...")
    github_result = release_manager.create_github_release(config, asset_result["commit_sha"])

    click.echo(click.style(f"GitHub release created: {github_result['tag_name']}", fg="green"))
    if github_result["release_url"]:
        click.echo(f"Release URL: {github_result['release_url']}")

    return github_result


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """BirdNET-Pi Release Management.

    Tools for creating releases with orphaned commit asset distribution.

    Examples:
      # Create release with default assets (models + IOC DB)
      release-manager create v2.0.0 --include-models --include-ioc-db

      # Create release with GitHub release
      release-manager create v2.0.0 --include-models --include-ioc-db --create-github-release

      # Create release with custom assets
      release-manager create v2.0.0 --custom-assets "/path/to/file:filename:Description"

      # List available assets
      release-manager list-assets
    """
    ctx.ensure_object(dict)
    ctx.obj["path_resolver"] = PathResolver()
    ctx.obj["release_manager"] = ReleaseManager(ctx.obj["path_resolver"])


@cli.command()
@click.argument("version")
@click.option("--include-models", is_flag=True, help="Include BirdNET models")
@click.option("--include-ioc-db", is_flag=True, help="Include IOC reference database")
@click.option("--include-avibase-db", is_flag=True, help="Include Avibase multilingual database")
@click.option(
    "--include-patlevin-db", is_flag=True, help="Include PatLevin BirdNET labels database"
)
@click.option(
    "--custom-assets",
    multiple=True,
    help="Custom assets (format: source_path:target_name:description)",
)
@click.option("--asset-branch", help="Name for the asset branch (default: assets-{version})")
@click.option("--commit-message", help="Commit message for the asset commit")
@click.option("--tag-name", help="Git tag name (default: v{version})")
@click.option("--create-github-release", is_flag=True, help="Create GitHub release")
@click.option("--output-json", help="Output release data to JSON file")
@click.pass_obj
def create(
    obj: dict[str, Any],
    version: str,
    include_models: bool,
    include_ioc_db: bool,
    include_avibase_db: bool,
    include_patlevin_db: bool,
    custom_assets: tuple[str, ...],
    asset_branch: str | None,
    commit_message: str | None,
    tag_name: str | None,
    create_github_release: bool,
    output_json: str | None,
) -> None:
    """Create a new release with assets.

    VERSION: Release version (e.g., v2.0.0)
    """
    release_manager = obj["release_manager"]

    # Build asset list
    assets = _build_asset_list(
        include_models,
        include_ioc_db,
        include_avibase_db,
        include_patlevin_db,
        custom_assets,
        release_manager,
    )

    # Create release configuration
    asset_branch_name = asset_branch or f"assets-{version}"
    commit_msg = commit_message or f"Release assets for BirdNET-Pi v{version}"

    config = ReleaseConfig(
        version=version,
        asset_branch_name=asset_branch_name,
        commit_message=commit_msg,
        assets=assets,
        tag_name=tag_name,
    )

    try:
        # Create asset release
        click.echo("Creating orphaned commit with release assets...")
        asset_result = release_manager.create_asset_release(config)

        click.echo()
        click.echo(click.style("✓ Asset release created successfully!", fg="green", bold=True))
        click.echo(f"  Version: {asset_result['version']}")
        click.echo(f"  Branch: {asset_result['asset_branch']}")
        click.echo(f"  Commit: {asset_result['commit_sha']}")
        click.echo(f"  Assets: {len(asset_result['assets'])}")

        # Create GitHub release if requested
        github_result = _handle_github_release(
            create_github_release, config, release_manager, asset_result
        )

        # Output JSON if requested
        if output_json:
            output_data = {
                "asset_release": asset_result,
                "github_release": github_result,
            }
            click.echo()
            click.echo(f"Release data written to: {output_json}")
            Path(output_json).write_text(json.dumps(output_data, indent=2))

    except Exception as e:
        click.echo(click.style(f"✗ Error creating release: {e}", fg="red", bold=True), err=True)
        sys.exit(1)


@cli.command("list-assets")
@click.pass_obj
def list_assets(obj: dict[str, Any]) -> None:
    """List available assets for release."""
    release_manager = obj["release_manager"]

    default_assets = release_manager.get_default_assets()

    click.echo("Available assets for release:")
    click.echo()

    for asset in default_assets:
        exists = Path(asset.source_path).exists()
        status_icon = "✓" if exists else "✗"
        color = "green" if exists else "red"
        size = ""

        if exists:
            if Path(asset.source_path).is_file():
                size_bytes = Path(asset.source_path).stat().st_size
                size = f" ({size_bytes / 1024 / 1024:.1f} MB)"
            elif Path(asset.source_path).is_dir():
                # Calculate directory size
                total_size = sum(
                    f.stat().st_size for f in Path(asset.source_path).rglob("*") if f.is_file()
                )
                size = f" ({total_size / 1024 / 1024:.1f} MB)"

        click.echo(click.style(f"  {status_icon} {asset.target_name}{size}", fg=color))
        click.echo(f"    Source: {asset.source_path}")
        click.echo(f"    Description: {asset.description}")
        click.echo()


def main() -> None:
    """Entry point for the release management CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
