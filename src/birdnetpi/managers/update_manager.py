import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

from birdnetpi.models.config import BirdNETConfig
from birdnetpi.utils.file_path_resolver import FilePathResolver


class UpdateManager:
    """Manages updates and Git operations for the BirdNET-Pi repository."""

    def __init__(self, file_resolver: FilePathResolver) -> None:
        self.file_resolver = file_resolver
        self.app_dir = file_resolver.app_dir

    def get_commits_behind(self) -> int:
        """Check how many commits the local repository is behind the remote."""
        try:
            # Git fetch to update remote tracking branches
            subprocess.run(
                ["git", "-C", str(self.app_dir), "fetch"], check=True, capture_output=True
            )

            # Git status to get the status of the repository
            result = subprocess.run(
                ["git", "-C", str(self.app_dir), "status"],
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

    def update_birdnet(self, config: BirdNETConfig) -> None:
        """Update the BirdNET-Pi repository to the latest version."""
        try:
            # Get current HEAD hash
            current_commit_hash = subprocess.run(
                ["git", "-C", str(self.app_dir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Reset current HEAD to remove any local changes
            subprocess.run(
                ["git", "-C", str(self.app_dir), "reset", "--hard"],
                check=True,
                capture_output=True,
            )

            # Fetches latest changes
            subprocess.run(
                ["git", "-C", str(self.app_dir), "fetch", config.git_remote, config.git_branch],
                check=True,
                capture_output=True,
            )

            # Switches git to specified branch
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.app_dir),
                    "switch",
                    "-C",
                    config.git_branch,
                    "--track",
                    f"{config.git_remote}/{config.git_branch}",
                ],
                check=True,
                capture_output=True,
            )

            # Prints out changes
            diff_output = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.app_dir),
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
            script_dir = self.app_dir / "scripts"
            if script_dir.exists():
                for script_path in script_dir.iterdir():
                    if script_path.is_file():
                        subprocess.run(
                            [
                                "sudo",
                                "ln",
                                "-sf",
                                str(script_path),
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

    def _resolve_version(self, version: str, github_repo: str) -> str:
        """Resolve version string to actual release tag."""
        if version != "latest":
            return version

        api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
        with httpx.Client() as client:
            response = client.get(api_url)
            response.raise_for_status()
            latest_release = response.json()
            return latest_release["tag_name"]

    def _resolve_latest_asset_version(self, github_repo: str) -> str:
        """Resolve 'latest' to the most recent asset release version."""
        try:
            api_url = f"https://api.github.com/repos/{github_repo}/releases"
            with httpx.Client() as client:
                response = client.get(api_url)
                response.raise_for_status()
                releases = response.json()

                # Find the latest release that starts with "assets-"
                asset_releases = [
                    release["tag_name"]
                    for release in releases
                    if release["tag_name"].startswith("assets-")
                ]

                if not asset_releases:
                    raise RuntimeError("No asset releases found")

                # Return the first (most recent) asset release, removing the "assets-" prefix
                latest_asset_tag = asset_releases[0]
                return latest_asset_tag.replace("assets-", "")

        except Exception as e:
            print(f"Failed to resolve latest asset version: {e}")
            raise

    def _validate_asset_release(self, version: str, github_repo: str) -> str:
        """Validate asset release exists and return asset tag name."""
        # Construct asset release tag (assets-v1.0.0 format)
        if version.startswith("v"):
            asset_tag = f"assets-{version}"
        else:
            asset_tag = f"assets-v{version}"

        # Check if asset release exists
        release_api_url = f"https://api.github.com/repos/{github_repo}/releases/tags/{asset_tag}"
        with httpx.Client() as client:
            response = client.get(release_api_url)
            if response.status_code == 404:
                available = ", ".join(self.list_available_asset_versions(github_repo))
                raise RuntimeError(
                    f"Asset release '{asset_tag}' not found. Available asset releases: {available}"
                )
            response.raise_for_status()

        return asset_tag

    def _download_and_extract_assets(self, asset_tag: str, github_repo: str) -> Path:
        """Download and extract asset archive from release tag, return extracted directory."""
        archive_url = f"https://github.com/{github_repo}/archive/{asset_tag}.tar.gz"
        print(f"Downloading assets from release tag {asset_tag}")

        temp_dir = Path(tempfile.mkdtemp())
        archive_path = temp_dir / "assets.tar.gz"

        # Download with progress bar
        with httpx.Client(follow_redirects=True, timeout=600.0) as client:
            with client.stream("GET", archive_url) as response:
                response.raise_for_status()
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

        # Extract archive
        extract_path = temp_dir / "extracted"
        shutil.unpack_archive(archive_path, extract_path)

        # Find extracted directory
        extracted_dirs = list(extract_path.iterdir())
        if not extracted_dirs:
            raise RuntimeError("No extracted directory found")

        return extracted_dirs[0]

    def download_release_assets(
        self,
        version: str = "latest",
        include_models: bool = True,
        include_ioc_db: bool = True,
        include_avibase_db: bool = False,
        include_patlevin_db: bool = False,
        github_repo: str = "mverteuil/BirdNET-Pi",
    ) -> dict[str, Any]:
        """Download models and databases from orphaned commit asset release.

        This method downloads assets from GitHub releases that use orphaned
        commits tagged as asset releases (e.g., assets-v1.0.0).

        Args:
            version: Asset release version (e.g., "v1.0.0" or "latest")
            include_models: Whether to download BirdNET models
            include_ioc_db: Whether to download IOC database
            include_avibase_db: Whether to download Avibase multilingual database
            include_patlevin_db: Whether to download PatLevin translations database
            github_repo: GitHub repository in format "owner/repo"

        Returns:
            Dictionary with download results and metadata
        """
        # For asset releases, we need to resolve to the latest asset version, not code version
        if version == "latest":
            version = self._resolve_latest_asset_version(github_repo)

        results = {"version": version, "downloaded_assets": [], "errors": []}

        try:
            asset_tag = self._validate_asset_release(version, github_repo)
            asset_source_dir = self._download_and_extract_assets(asset_tag, github_repo)

            # Download models if requested
            if include_models:
                models_source = asset_source_dir / "data" / "models"
                if models_source.exists():
                    models_target = self.file_resolver.get_models_dir()
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
                ioc_source = asset_source_dir / "data" / "database" / "ioc_reference.db"
                if ioc_source.exists():
                    ioc_target = self.file_resolver.get_ioc_database_path()
                    ioc_target.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(ioc_source, ioc_target)
                    results["downloaded_assets"].append("IOC reference database")

                    print(f"Downloaded IOC database to {ioc_target}")
                else:
                    results["errors"].append("IOC database not found in release")

            # Download Avibase database if requested
            if include_avibase_db:
                avibase_source = asset_source_dir / "data" / "database" / "avibase_database.db"
                if avibase_source.exists():
                    avibase_target = self.file_resolver.get_avibase_database_path()
                    avibase_target.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(avibase_source, avibase_target)
                    results["downloaded_assets"].append("Avibase multilingual database")

                    print(f"Downloaded Avibase database to {avibase_target}")
                else:
                    results["errors"].append("Avibase database not found in release")

            # Download PatLevin database if requested
            if include_patlevin_db:
                patlevin_source = asset_source_dir / "data" / "database" / "patlevin_database.db"
                if patlevin_source.exists():
                    patlevin_target = self.file_resolver.get_patlevin_database_path()
                    patlevin_target.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(patlevin_source, patlevin_target)
                    results["downloaded_assets"].append("PatLevin translations database")

                    print(f"Downloaded PatLevin database to {patlevin_target}")
                else:
                    results["errors"].append("PatLevin database not found in release")

            print(f"Asset download completed for version {version}")
            return results

        except Exception as e:
            error_msg = f"Failed to download assets: {e}"
            results["errors"].append(error_msg)
            print(error_msg)
            raise

    def list_available_versions(self, github_repo: str = "mverteuil/BirdNET-Pi") -> list[str]:
        """List available code release versions.

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

                # Filter out asset releases, only return code releases
                versions = [
                    release["tag_name"]
                    for release in releases
                    if not release["tag_name"].startswith("assets-")
                ]
                return versions

        except Exception as e:
            print(f"Failed to list versions: {e}")
            return []

    def list_available_asset_versions(self, github_repo: str = "mverteuil/BirdNET-Pi") -> list[str]:
        """List available asset release versions.

        Args:
            github_repo: GitHub repository in format "owner/repo"

        Returns:
            List of available asset version tags (with assets- prefix removed)
        """
        try:
            api_url = f"https://api.github.com/repos/{github_repo}/releases"
            with httpx.Client() as client:
                response = client.get(api_url)
                response.raise_for_status()
                releases = response.json()

                # Filter for asset releases and remove the "assets-" prefix
                asset_versions = [
                    release["tag_name"].replace("assets-", "")
                    for release in releases
                    if release["tag_name"].startswith("assets-")
                ]
                return asset_versions

        except Exception as e:
            print(f"Failed to list asset versions: {e}")
            return []
