import argparse
import os

from birdnetpi.managers.update_manager import UpdateManager
from birdnetpi.models.git_update_config import GitUpdateConfig


def main_cli() -> None:
    """Provide the main entry point for the Update Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Update Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., update_birdnet, update_caddyfile)",
    )
    parser.add_argument(
        "-r", "--remote", type=str, default="origin", help="Git remote to use"
    )
    parser.add_argument(
        "-b", "--branch", type=str, default="main", help="Git branch to use"
    )
    parser.add_argument("--birdnetpi_url", type=str, help="URL for BirdNET-Pi")
    parser.add_argument("--extracted_path", type=str, help="Path to extracted files")
    parser.add_argument("--caddy_pwd", type=str, help="Password for Caddy")

    args = parser.parse_args()

    update_manager = UpdateManager()

    if args.action == "update_birdnet":
        git_update_config = GitUpdateConfig(remote=args.remote, branch=args.branch)
        update_manager.update_birdnet(git_update_config)
    elif args.action == "update_caddyfile":
        birdnetpi_url = args.birdnetpi_url or os.environ.get("BIRDNETPI_URL")
        extracted_path = args.extracted_path or os.environ.get("EXTRACTED")
        caddy_pwd = args.caddy_pwd or os.environ.get("CADDY_PWD")
        if not birdnetpi_url or not extracted_path:
            parser.error(
                "--birdnetpi_url and --extracted_path are required for "
                "update_caddyfile action."
            )
        update_manager.update_caddyfile(
            birdnetpi_url=birdnetpi_url,
            extracted_path=extracted_path,
            caddy_pwd=caddy_pwd,
        )
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
