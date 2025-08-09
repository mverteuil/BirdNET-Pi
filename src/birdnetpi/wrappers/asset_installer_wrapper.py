"""CLI wrapper for installing BirdNET-Pi assets from releases.

This script provides command-line access to download and install
models and IOC database from orphaned commit releases for local
development and CI environments.
"""

import argparse
import json
import sys
from pathlib import Path

from birdnetpi.managers.update_manager import UpdateManager
from birdnetpi.utils.file_path_resolver import FilePathResolver


def install_assets(args: argparse.Namespace) -> None:
    """Install assets from a release."""
    update_manager = UpdateManager()

    print(f"Installing assets for version: {args.version}")

    if not args.include_models and not args.include_ioc_db:
        print("Error: Must specify at least one asset type (--include-models or --include-ioc-db)")
        sys.exit(1)

    try:
        result = update_manager.download_release_assets(
            version=args.version,
            include_models=args.include_models,
            include_ioc_db=args.include_ioc_db,
            github_repo="mverteuil/BirdNET-Pi",
        )

        print("\nAsset installation completed successfully!")
        print(f"  Version: {result['version']}")
        print(f"  Downloaded assets: {len(result['downloaded_assets'])}")

        for asset in result["downloaded_assets"]:
            print(f"    • {asset}")

        # Output JSON if requested
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(result, indent=2))
            print(f"\nInstallation data written to: {args.output_json}")

    except Exception as e:
        error_msg = str(e)
        print(f"Error installing assets: {error_msg}")

        # Show helpful local development message for permission errors
        if "Permission denied" in error_msg and "/var/lib/birdnetpi" in error_msg:
            print()
            print("┌" + "─" * 78 + "┐")
            print("│" + " " * 78 + "│")
            print("│  🛠️  LOCAL DEVELOPMENT SETUP REQUIRED" + " " * 39 + "│")
            print("│" + " " * 78 + "│")
            print(
                "│  For local development, you need to set the BIRDNETPI_DATA environment"
                + " " * 5
                + "│"
            )
            print(
                "│  variable to a writable directory (e.g., ./data in your project root)."
                + " " * 4
                + "│"
            )
            print("│" + " " * 78 + "│")
            print("│  Run the asset installer with:" + " " * 44 + "│")
            print("│    export BIRDNETPI_DATA=./data" + " " * 43 + "│")
            print("│    uv run asset-installer install v2.1.0 --include-models --include-ioc-db│")
            print("│" + " " * 78 + "│")
            print(
                "│  Or set it permanently in your shell profile (e.g., ~/.bashrc):" + " " * 12 + "│"
            )
            print("│    echo 'export BIRDNETPI_DATA=./data' >> ~/.bashrc" + " " * 24 + "│")
            print("│" + " " * 78 + "│")
            print("└" + "─" * 78 + "┘")
            print()

        sys.exit(1)


def list_available_assets(args: argparse.Namespace) -> None:
    """List available asset versions."""
    update_manager = UpdateManager()

    try:
        versions = update_manager.list_available_versions(github_repo="mverteuil/BirdNET-Pi")

        print("Available asset versions:")
        print()

        if not versions:
            print("  No asset versions found.")
            return

        print(f"Latest version: {versions[0] if versions else 'None'}")
        print()

        for version in versions:
            print(f"  • {version}")

    except Exception as e:
        print(f"Error listing available assets: {e}")
        sys.exit(1)


def check_local_assets(args: argparse.Namespace) -> None:
    """Check status of locally installed assets."""
    file_resolver = FilePathResolver()

    print("Local asset status:")
    print()

    # Check models
    models_dir = Path(file_resolver.get_models_dir())
    if models_dir.exists():
        model_files = list(models_dir.rglob("*.tflite"))
        total_size = sum(f.stat().st_size for f in models_dir.rglob("*") if f.is_file())
        size_mb = total_size / 1024 / 1024

        print(f"  ✓ Models: {len(model_files)} model files ({size_mb:.1f} MB)")
        print(f"    Location: {models_dir}")

        if args.verbose:
            for model_file in sorted(model_files):
                file_size = model_file.stat().st_size / 1024 / 1024
                print(f"      - {model_file.name} ({file_size:.1f} MB)")
    else:
        print("  ✗ Models: Not installed")
        print(f"    Expected location: {models_dir}")

    print()

    # Check IOC database
    ioc_db_path = Path(file_resolver.get_ioc_database_path())
    if ioc_db_path.exists():
        file_size = ioc_db_path.stat().st_size / 1024 / 1024
        print(f"  ✓ IOC Database: {file_size:.1f} MB")
        print(f"    Location: {ioc_db_path}")
    else:
        print("  ✗ IOC Database: Not installed")
        print(f"    Expected location: {ioc_db_path}")

    print()


def main() -> None:
    """Run the asset installer CLI."""
    parser = argparse.ArgumentParser(
        description="BirdNET-Pi Asset Installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Install latest models and all databases
  asset-installer install latest --include-models --include-ioc-db --include-avibase-db --include-patlevin-db

  # Install only models for a specific version
  asset-installer install v2.1.0 --include-models

  # List available versions
  asset-installer list-versions

  # Check what's currently installed
  asset-installer check-local
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    install_parser = subparsers.add_parser("install", help="Install assets from a release")
    install_parser.add_argument(
        "version", help="Release version to install (e.g., 'v2.0.0' or 'latest')"
    )
    install_parser.add_argument(
        "--include-models", action="store_true", help="Include BirdNET TensorFlow Lite models"
    )
    install_parser.add_argument(
        "--include-ioc-db",
        action="store_true",
        help="Include IOC World Bird Names reference database",
    )
    install_parser.add_argument(
        "--remote", default="origin", help="Git remote to fetch from (default: origin)"
    )
    install_parser.add_argument("--output-json", help="Output installation data to JSON file")

    # List versions command
    list_parser = subparsers.add_parser("list-versions", help="List available asset versions")
    list_parser.add_argument(
        "--remote", default="origin", help="Git remote to check (default: origin)"
    )

    # Check local command
    check_parser = subparsers.add_parser("check-local", help="Check locally installed assets")
    check_parser.add_argument(
        "--verbose", action="store_true", help="Show detailed file information"
    )

    args = parser.parse_args()

    if args.command == "install":
        install_assets(args)
    elif args.command == "list-versions":
        list_available_assets(args)
    elif args.command == "check-local":
        check_local_assets(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
