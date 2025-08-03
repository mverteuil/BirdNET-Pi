import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

from birdnetpi.models.config import GitUpdateConfig
from birdnetpi.utils.file_path_resolver import FilePathResolver


class UpdateManager:
    """Manages updates and Git operations for the BirdNET-Pi repository."""

    def __init__(self) -> None:
        self.repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    def get_commits_behind(self) -> int:
        """Check how many commits the local repository is behind the remote."""
        try:
            # Git fetch to update remote tracking branches
            subprocess.run(["git", "-C", self.repo_path, "fetch"], check=True, capture_output=True)

            # Git status to get the status of the repository
            result = subprocess.run(
                ["git", "-C", self.repo_path, "status"],
                check=True,
                capture_output=True,
                text=True,
            )
            status_output = result.stdout

            # Regex to find "behind 'origin/branch' by X commits"
            match_behind = re.search(r"behind '[^']+' by (\d+) commit", status_output)
            if match_behind:
                return int(match_behind.group(1))

            # Regex to find "X and Y different commits each"
            match_diverged = re.search(r"(\d+) and (\d+) different commits each", status_output)
            if match_diverged:
                return int(match_diverged.group(1)) + int(match_diverged.group(2))

            return 0  # No commits behind
        except subprocess.CalledProcessError as e:
            print(f"Error executing git command: {e.stderr}")
            return -1  # Indicate an error
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return -1  # Indicate an error

    def update_birdnet(self, config: GitUpdateConfig) -> None:
        """Update the BirdNET-Pi repository to the latest version."""
        try:
            # Get current HEAD hash
            current_commit_hash = subprocess.run(
                ["git", "-C", self.repo_path, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Reset current HEAD to remove any local changes
            subprocess.run(
                ["git", "-C", self.repo_path, "reset", "--hard"],
                check=True,
                capture_output=True,
            )

            # Fetches latest changes
            subprocess.run(
                ["git", "-C", self.repo_path, "fetch", config.remote, config.branch],
                check=True,
                capture_output=True,
            )

            # Switches git to specified branch
            subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo_path,
                    "switch",
                    "-C",
                    config.branch,
                    "--track",
                    f"{config.remote}/{config.branch}",
                ],
                check=True,
                capture_output=True,
            )

            # Prints out changes
            diff_output = subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo_path,
                    "diff",
                    "--stat",
                    current_commit_hash,
                    "HEAD",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout

            print(diff_output)

            # Reload systemd daemon
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)

            # Symlink scripts
            script_dir = os.path.join(self.repo_path, "scripts")
            for script in os.listdir(script_dir):
                if os.path.isfile(os.path.join(script_dir, script)):
                    subprocess.run(
                        [
                            "sudo",
                            "ln",
                            "-sf",
                            os.path.join(script_dir, script),
                            "/usr/local/bin/",
                        ],
                        check=True,
                    )

        except subprocess.CalledProcessError as e:
            print(f"Error during BirdNET-Pi update: {e.stderr}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during update: {e}")
            raise

    def download_release_assets(
        self,
        version: str = "latest",
        include_models: bool = True,
        include_ioc_db: bool = True,
        github_repo: str = "mverteuil/BirdNET-Pi",
    ) -> dict[str, Any]:
        """Download models and IOC database from orphaned commit release.

        This method downloads assets from GitHub releases that use the orphaned
        commit strategy for distributing large files.

        Args:
            version: Release version (e.g., "v2.0.0" or "latest")
            include_models: Whether to download BirdNET models
            include_ioc_db: Whether to download IOC database
            github_repo: GitHub repository in format "owner/repo"

        Returns:
            Dictionary with download results and metadata
        """
        file_resolver = FilePathResolver()
        results = {"version": version, "downloaded_assets": [], "errors": []}

        try:
            # Determine the commit SHA for the version
            if version == "latest":
                # Get the latest release tag
                api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
                with httpx.Client() as client:
                    response = client.get(api_url)
                    response.raise_for_status()
                    latest_release = response.json()
                    version = latest_release["tag_name"]
                    results["version"] = version

            # The asset branch follows the pattern "assets-{version}"
            asset_branch = f"assets-{version}"
            archive_url = f"https://github.com/{github_repo}/archive/{asset_branch}.tar.gz"

            print(f"Downloading assets for version {version} from {archive_url}")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                archive_path = temp_path / "assets.tar.gz"

                # Download the asset archive with progress bar (extended timeout for large files)
                with httpx.Client(follow_redirects=True, timeout=600.0) as client:
                    with client.stream("GET", archive_url) as response:
                        response.raise_for_status()

                        # Get the total file size if available
                        total_size = int(response.headers.get("content-length", 0))

                        with open(archive_path, "wb") as f:
                            with tqdm(
                                total=total_size,
                                unit="B",
                                unit_scale=True,
                                unit_divisor=1024,
                                desc="Downloading assets",
                            ) as progress:
                                for chunk in response.iter_bytes(chunk_size=8192):
                                    f.write(chunk)
                                    progress.update(len(chunk))

                # Extract the archive
                extract_path = temp_path / "extracted"
                shutil.unpack_archive(archive_path, extract_path)

                # Find the extracted directory (it will be named like "BirdNET-Pi-assets-v2.0.0")
                extracted_dirs = list(extract_path.iterdir())
                if not extracted_dirs:
                    raise RuntimeError("No extracted directory found")

                asset_source_dir = extracted_dirs[0]

                # Download models if requested
                if include_models:
                    models_source = asset_source_dir / "data" / "models"
                    if models_source.exists():
                        models_target = Path(file_resolver.get_models_dir())
                        models_target.mkdir(parents=True, exist_ok=True)

                        # Copy all model files
                        for model_file in models_source.glob("*.tflite"):
                            target_file = models_target / model_file.name
                            shutil.copy2(model_file, target_file)
                            results["downloaded_assets"].append(f"Model: {model_file.name}")

                        print(f"Downloaded models to {models_target}")
                    else:
                        results["errors"].append("Models directory not found in release")

                # Download IOC database if requested
                if include_ioc_db:
                    ioc_source = asset_source_dir / "data" / "ioc_reference.db"
                    if ioc_source.exists():
                        ioc_target = Path(file_resolver.get_ioc_database_path())
                        ioc_target.parent.mkdir(parents=True, exist_ok=True)

                        shutil.copy2(ioc_source, ioc_target)
                        results["downloaded_assets"].append("IOC reference database")

                        print(f"Downloaded IOC database to {ioc_target}")
                    else:
                        results["errors"].append("IOC database not found in release")

            print(f"Asset download completed for version {version}")
            return results

        except Exception as e:
            error_msg = f"Failed to download assets: {e}"
            results["errors"].append(error_msg)
            print(error_msg)
            raise

    def list_available_versions(self, github_repo: str = "mverteuil/BirdNET-Pi") -> list[str]:
        """List available asset release versions.

        Args:
            github_repo: GitHub repository in format "owner/repo"

        Returns:
            List of available version tags
        """
        try:
            api_url = f"https://api.github.com/repos/{github_repo}/releases"
            with httpx.Client() as client:
                response = client.get(api_url)
                response.raise_for_status()
                releases = response.json()

                versions = [release["tag_name"] for release in releases]
                return versions

        except Exception as e:
            print(f"Failed to list versions: {e}")
            return []

    from birdnetpi.models.config import CaddyConfig

    def update_caddyfile(self, config: CaddyConfig) -> None:
        """Update the Caddyfile with new configuration and reload Caddy."""
        try:
            # Ensure /etc/caddy exists
            subprocess.run(["sudo", "mkdir", "-p", "/etc/caddy"], check=True)

            caddyfile_path = "/etc/caddy/Caddyfile"

            # Backup existing Caddyfile if it exists
            if os.path.exists(caddyfile_path):
                subprocess.run(
                    ["sudo", "cp", caddyfile_path, f"{caddyfile_path}.original"],
                    check=True,
                )

            caddyfile_content = (
                f"http:// {config.birdnetpi_url} {{\n"
                "  reverse_proxy localhost:8000\n"
                "  reverse_proxy /log* localhost:8080\n"
                "  reverse_proxy /stats* localhost:8501\n"
                "  reverse_proxy /terminal* localhost:8888\n"
                "}\n"
            )

            # Write the Caddyfile content
            # Using a temporary file and then moving it with sudo to handle permissions
            temp_caddyfile_path = "/tmp/Caddyfile_temp"
            with open(temp_caddyfile_path, "w") as f:
                f.write(caddyfile_content)
            subprocess.run(["sudo", "mv", temp_caddyfile_path, caddyfile_path], check=True)

            # Format and reload Caddy
            subprocess.run(["sudo", "caddy", "fmt", "--overwrite", caddyfile_path], check=True)
            subprocess.run(["sudo", "systemctl", "reload", "caddy"], check=True)

            print("Caddyfile updated and Caddy reloaded successfully.")

        except subprocess.CalledProcessError as e:
            print(f"Error updating Caddyfile: {e.stderr}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during Caddyfile update: {e}")
            raise
