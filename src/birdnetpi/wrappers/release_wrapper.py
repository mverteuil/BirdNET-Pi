"""CLI wrapper for release management operations.

This script provides command-line access to the ReleaseManager functionality
for creating automated releases with orphaned commit asset distribution.
"""

import argparse
import json
import sys
from pathlib import Path

from birdnetpi.managers.release_manager import ReleaseAsset, ReleaseConfig, ReleaseManager
from birdnetpi.utils.file_path_resolver import FilePathResolver


def _add_asset_if_requested(
    args: argparse.Namespace,
    attr_name: str,
    filename_pattern: str,
    warning_msg: str,
    default_assets: list[ReleaseAsset],
    assets: list[ReleaseAsset],
) -> None:
    """Add asset if requested and found."""
    if not getattr(args, attr_name, False):
        return

    asset = next((a for a in default_assets if filename_pattern in str(a.target_name)), None)
    if asset and Path(asset.source_path).exists():
        assets.append(asset)
    else:
        print(f"Warning: {warning_msg}")


def _build_asset_list(
    args: argparse.Namespace, release_manager: ReleaseManager
) -> list[ReleaseAsset]:
    """Build the list of assets for the release."""
    assets = []
    default_assets = release_manager.get_default_assets()

    # Map of arguments to their corresponding asset patterns and warnings
    asset_configs = [
        ("include_models", "models", "Models not found at expected locations"),
        ("include_ioc_db", "ioc_reference.db", "IOC database not found at expected locations"),
        (
            "include_avibase_db",
            "avibase_database.db",
            "Avibase database not found at expected locations",
        ),
        (
            "include_patlevin_db",
            "patlevin_database.db",
            "PatLevin database not found at expected locations",
        ),
    ]

    for attr_name, pattern, warning in asset_configs:
        _add_asset_if_requested(args, attr_name, pattern, warning, default_assets, assets)

    # Add custom assets
    if args.custom_assets:
        _add_custom_assets(args.custom_assets, assets)

    if not assets:
        print("Error: No assets specified for release")
        sys.exit(1)

    return assets


def _add_custom_assets(custom_assets: list[str], assets: list[ReleaseAsset]) -> None:
    """Add custom assets to the asset list."""
    for asset_spec in custom_assets:
        parts = asset_spec.split(":")
        if len(parts) != 3:
            print(f"Error: Invalid asset specification: {asset_spec}")
            print("Format: source_path:target_name:description")
            sys.exit(1)

        source_path, target_name, description = parts
        if not Path(source_path).exists():
            print(f"Error: Asset not found: {source_path}")
            sys.exit(1)

        assets.append(ReleaseAsset(Path(source_path), Path(target_name), description))


def _handle_github_release(
    args: argparse.Namespace,
    config: ReleaseConfig,
    release_manager: ReleaseManager,
    asset_result: dict,
) -> dict | None:
    """Create GitHub release if requested."""
    if not args.create_github_release:
        return None

    print("\nCreating GitHub release...")
    github_result = release_manager.create_github_release(config, asset_result["commit_sha"])

    print(f"GitHub release created: {github_result['tag_name']}")
    if github_result["release_url"]:
        print(f"Release URL: {github_result['release_url']}")

    return github_result


def create_release(args: argparse.Namespace) -> None:
    """Create a new release with assets."""
    file_resolver = FilePathResolver()
    release_manager = ReleaseManager(file_resolver)

    # Build asset list
    assets = _build_asset_list(args, release_manager)

    # Create release configuration
    asset_branch_name = args.asset_branch or f"assets-{args.version}"
    commit_message = args.commit_message or f"Release assets for BirdNET-Pi v{args.version}"

    config = ReleaseConfig(
        version=args.version,
        asset_branch_name=asset_branch_name,
        commit_message=commit_message,
        assets=assets,
        tag_name=args.tag_name,
    )

    try:
        # Create asset release
        print("Creating orphaned commit with release assets...")
        asset_result = release_manager.create_asset_release(config)

        print("\nAsset release created successfully!")
        print(f"  Version: {asset_result['version']}")
        print(f"  Branch: {asset_result['asset_branch']}")
        print(f"  Commit: {asset_result['commit_sha']}")
        print(f"  Assets: {len(asset_result['assets'])}")

        # Create GitHub release if requested
        github_result = _handle_github_release(args, config, release_manager, asset_result)

        # Output JSON if requested
        if args.output_json:
            output_data = {
                "asset_release": asset_result,
                "github_release": github_result,
            }
            print(f"\nRelease data written to: {args.output_json}")
            Path(args.output_json).write_text(json.dumps(output_data, indent=2))

    except Exception as e:
        print(f"Error creating release: {e}")
        sys.exit(1)


def list_assets(args: argparse.Namespace) -> None:
    """List available assets for release."""
    file_resolver = FilePathResolver()
    release_manager = ReleaseManager(file_resolver)

    default_assets = release_manager.get_default_assets()

    print("Available assets for release:")
    print()

    for asset in default_assets:
        exists = "✓" if Path(asset.source_path).exists() else "✗"
        size = ""
        if Path(asset.source_path).exists():
            if Path(asset.source_path).is_file():
                size_bytes = Path(asset.source_path).stat().st_size
                size = f" ({size_bytes / 1024 / 1024:.1f} MB)"
            elif Path(asset.source_path).is_dir():
                # Calculate directory size
                total_size = sum(
                    f.stat().st_size for f in Path(asset.source_path).rglob("*") if f.is_file()
                )
                size = f" ({total_size / 1024 / 1024:.1f} MB)"

        print(f"  {exists} {asset.target_name}{size}")
        print(f"    Source: {asset.source_path}")
        print(f"    Description: {asset.description}")
        print()


def main() -> None:
    """Run the release management CLI."""
    parser = argparse.ArgumentParser(
        description="BirdNET-Pi Release Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create release with default assets (models + IOC DB)
  release-manager create v2.0.0 --include-models --include-ioc-db

  # Create release with GitHub release
  release-manager create v2.0.0 --include-models --include-ioc-db --create-github-release

  # Create release with custom assets
  release-manager create v2.0.0 --custom-assets "/path/to/file:filename:Description"

  # List available assets
  release-manager list-assets
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create release command
    create_parser = subparsers.add_parser("create", help="Create a new release")
    create_parser.add_argument("version", help="Release version (e.g., v2.0.0)")
    create_parser.add_argument(
        "--include-models", action="store_true", help="Include BirdNET models"
    )
    create_parser.add_argument(
        "--include-ioc-db", action="store_true", help="Include IOC reference database"
    )
    create_parser.add_argument(
        "--include-avibase-db", action="store_true", help="Include Avibase multilingual database"
    )
    create_parser.add_argument(
        "--include-patlevin-db",
        action="store_true",
        help="Include PatLevin BirdNET labels database",
    )
    create_parser.add_argument(
        "--custom-assets",
        nargs="*",
        help="Custom assets (format: source_path:target_name:description)",
    )
    create_parser.add_argument(
        "--asset-branch", help="Name for the asset branch (default: assets-{version})"
    )
    create_parser.add_argument("--commit-message", help="Commit message for the asset commit")
    create_parser.add_argument("--tag-name", help="Git tag name (default: v{version})")
    create_parser.add_argument(
        "--create-github-release", action="store_true", help="Create GitHub release"
    )
    create_parser.add_argument("--output-json", help="Output release data to JSON file")

    # List assets command
    subparsers.add_parser("list-assets", help="List available assets")

    args = parser.parse_args()

    if args.command == "create":
        create_release(args)
    elif args.command == "list-assets":
        list_assets(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
