import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from alembic.config import Config
from sqlalchemy import create_engine, text
from tqdm import tqdm

from alembic import command
from birdnetpi.config import BirdNETConfig
from birdnetpi.releases.asset_manifest import AssetManifest, AssetType
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.system_control import SystemControlService


class StateFileManager:
    """Manages update state via FileManager and atomic file operations."""

    def __init__(self, file_manager: FileManager, path_resolver: PathResolver):
        """Initialize StateFileManager with dependencies.

        Args:
            file_manager: FileManager instance for atomic operations
            path_resolver: PathResolver instance for path resolution
        """
        self.file_manager = file_manager
        self.state_path = path_resolver.get_update_state_path()
        self.lock_path = path_resolver.get_update_lock_path()

    def write_state(self, state: dict) -> None:
        """Atomically write state to file.

        Args:
            state: State dictionary to write
        """
        state["updated_at"] = datetime.now().isoformat()
        # Atomic write: write to temp, then rename
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state, indent=2))
        temp_path.rename(self.state_path)  # Atomic on POSIX

    def read_state(self) -> dict | None:
        """Read current state if exists.

        Returns:
            State dictionary or None if no state exists
        """
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def clear_state(self) -> None:
        """Remove state file."""
        if self.state_path.exists():
            self.state_path.unlink()

    def acquire_lock(self, pid: int | None = None) -> bool:
        """Acquire update lock with PID.

        Args:
            pid: Process ID to write to lock file (defaults to current PID)

        Returns:
            True if lock acquired, False if already locked
        """
        if self.lock_path.exists():
            # Check if process is still running
            try:
                existing_pid = int(self.lock_path.read_text().strip())
                # Check if process exists
                os.kill(existing_pid, 0)
                return False  # Process still running
            except (ValueError, OSError, ProcessLookupError):
                # Invalid PID or process not running
                self.lock_path.unlink()

        # Write our PID
        pid = pid or os.getpid()
        self.lock_path.write_text(str(pid))
        return True

    def release_lock(self) -> None:
        """Release update lock."""
        if self.lock_path.exists():
            self.lock_path.unlink()


class UpdateManager:
    """Manages updates and Git operations for the BirdNET-Pi repository."""

    path_resolver: PathResolver
    app_dir: Path
    file_manager: FileManager
    system_control: SystemControlService
    state_manager: StateFileManager

    def __init__(
        self,
        path_resolver: PathResolver,
        file_manager: FileManager | None = None,
        system_control: SystemControlService | None = None,
    ) -> None:
        self.path_resolver = path_resolver
        self.app_dir = path_resolver.app_dir
        self.file_manager = file_manager or FileManager(path_resolver)
        self.system_control = system_control or SystemControlService()
        self.state_manager = StateFileManager(self.file_manager, path_resolver)

    def get_commits_behind(self, config: BirdNETConfig) -> int:
        """Check how many commits the local repository is behind the remote."""
        try:
            # Git fetch to update remote tracking branches
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.app_dir),
                    "fetch",
                    config.updates.git_remote,
                    config.updates.git_branch,
                ],
                check=True,
                capture_output=True,
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
                [
                    "git",
                    "-C",
                    str(self.app_dir),
                    "fetch",
                    config.updates.git_remote,
                    config.updates.git_branch,
                ],
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
                    config.updates.git_branch,
                    "--track",
                    f"{config.updates.git_remote}/{config.updates.git_branch}",
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

            # Reload system daemon configuration (systemd or supervisord)
            self.system_control.daemon_reload()

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

    def _download_models(self, asset_source_dir: Path, results: dict[str, Any]) -> None:
        """Download model files from asset source."""
        models_source = asset_source_dir / "data" / "models"
        if not models_source.exists():
            results["errors"].append("Models directory not found in release")
            return

        models_target = self.path_resolver.get_models_dir()
        models_target.mkdir(parents=True, exist_ok=True)

        # Copy all model files (.tflite and .txt labels)
        for pattern in ["*.tflite", "*.txt"]:
            for model_file in models_source.glob(pattern):
                target_file = models_target / model_file.name
                shutil.copy2(model_file, target_file)
                file_type = "Model" if model_file.suffix == ".tflite" else "Labels"
                results["downloaded_assets"].append(f"{file_type}: {model_file.name}")

        print(f"Downloaded models to {models_target}")

    def _download_database(
        self,
        asset_source_dir: Path,
        db_filename: str,
        target_path: Path,
        display_name: str,
        results: dict[str, Any],
    ) -> None:
        """Download a database file from asset source."""
        db_source = asset_source_dir / "data" / "database" / db_filename
        if not db_source.exists():
            results["errors"].append(f"{display_name} not found in release")
            return

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_source, target_path)
        results["downloaded_assets"].append(display_name)
        print(f"Downloaded {display_name} to {target_path}")

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

            # Use AssetManifest to determine what to download
            asset_flags = {
                "BirdNET Models": include_models,
                "IOC Reference Database": include_ioc_db,
                "Avibase Database": include_avibase_db,
                "PatLevin Database": include_patlevin_db,
            }

            # Get all assets from manifest
            for asset in AssetManifest.get_all_assets():
                if asset_flags.get(asset.name, False):
                    # Get the path for this asset
                    method = getattr(self.path_resolver, asset.path_method)
                    target_path = method()

                    if asset.asset_type == AssetType.MODEL:
                        self._download_models(asset_source_dir, results)
                    else:
                        # For databases, determine the source filename
                        if "ioc" in asset.name.lower():
                            db_filename = "ioc_reference.db"
                        elif "avibase" in asset.name.lower():
                            db_filename = "avibase_database.db"
                        elif "patlevin" in asset.name.lower():
                            db_filename = "patlevin_database.db"
                        else:
                            continue

                        self._download_database(
                            asset_source_dir, db_filename, target_path, asset.description, results
                        )

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

    async def check_for_updates(self) -> dict:
        """Check for available updates.

        Returns:
            Dictionary with update status and available versions
        """
        # Always get current version first (this should never fail)
        try:
            current_version = self.get_current_version()
        except Exception:
            current_version = "unknown"

        # Determine version type based on current version format
        # Development versions start with "dev-", release versions are tags like "v1.0.0"
        version_type = "development" if current_version.startswith("dev-") else "release"

        try:
            # Get latest version from remote (needs config for git remote)
            # This needs to be fixed to pass config
            # For now, create a minimal config with defaults
            config = BirdNETConfig()
            latest_version = self.get_latest_version(config)

            # Check if update is available
            update_available = self._is_newer_version(latest_version, current_version)

            return {
                "current_version": current_version,
                "latest_version": latest_version,
                "update_available": update_available,
                "version_type": version_type,
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as e:
            # Even on error, include current version info so dev banner can show
            return {
                "current_version": current_version,
                "version_type": version_type,
                "error": f"Failed to get latest version: {e}",
                "checked_at": datetime.now().isoformat(),
            }

    def get_current_version(self) -> str:
        """Get current application version from git tag or commit.

        Returns:
            Version string (tag or commit hash)
        """
        try:
            # Try to get current tag
            result = subprocess.run(
                ["git", "-C", str(self.app_dir), "describe", "--exact-match", "--tags"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()

            # Fall back to commit hash
            result = subprocess.run(
                ["git", "-C", str(self.app_dir), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return f"dev-{result.stdout.strip()}"
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get current version: {e}") from e

    def get_latest_version(self, config: BirdNETConfig) -> str:
        """Get latest version from remote repository.

        Returns:
            Latest version tag
        """
        try:
            # Get all tags from remote without fetching
            result = subprocess.run(
                ["git", "-C", str(self.app_dir), "ls-remote", "--tags", config.updates.git_remote],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse output to get tags
            tags = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    # Format: hash<tab>refs/tags/tagname
                    parts = line.split("\t")
                    if len(parts) == 2 and "refs/tags/" in parts[1]:
                        tag = parts[1].replace("refs/tags/", "")
                        # Skip annotated tag markers (^{})
                        if not tag.endswith("^{}"):
                            tags.append(tag)

            if not tags:
                raise RuntimeError("No tags found in remote repository")

            # Sort tags to get the latest (assumes semantic versioning)
            tags.sort(
                key=lambda x: [int(p) if p.isdigit() else p for p in x.replace("v", "").split(".")]
            )
            return tags[-1]
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get latest version: {e}") from e

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Check if latest version is newer than current.

        Args:
            latest: Latest version string
            current: Current version string

        Returns:
            True if latest is newer than current
        """
        # Handle development versions
        if current.startswith("dev-"):
            return True  # Development versions are always considered outdated

        # Simple version comparison
        return latest != current and latest > current

    async def apply_update(self, version: str) -> dict:
        """Apply an update to the specified version.

        Args:
            version: Target version to update to

        Returns:
            Dictionary with update result
        """
        # Check if update is already in progress
        if not self.state_manager.acquire_lock():
            return {"success": False, "error": "Update already in progress"}

        rollback_info: dict | None = None
        try:
            # Write initial state
            self.state_manager.write_state(
                {
                    "phase": "starting",
                    "target_version": version,
                    "started_at": datetime.now().isoformat(),
                }
            )

            # Create rollback point
            rollback_info = await self._create_rollback_point()
            self.state_manager.write_state(
                {
                    "phase": "rollback_created",
                    "target_version": version,
                    "rollback": rollback_info,
                }
            )

            # Perform git update
            self.state_manager.write_state(
                {
                    "phase": "updating_code",
                    "target_version": version,
                }
            )
            await self._perform_git_update(version)

            # Update dependencies
            self.state_manager.write_state(
                {
                    "phase": "updating_dependencies",
                    "target_version": version,
                }
            )
            await self._update_dependencies()

            # Run migrations
            self.state_manager.write_state(
                {
                    "phase": "running_migrations",
                    "target_version": version,
                }
            )
            await self._run_migrations()

            # Restart services
            self.state_manager.write_state(
                {
                    "phase": "restarting_services",
                    "target_version": version,
                }
            )
            await self._restart_services()

            # Update complete
            self.state_manager.write_state(
                {
                    "phase": "complete",
                    "target_version": version,
                    "completed_at": datetime.now().isoformat(),
                }
            )

            return {"success": True, "version": version}

        except Exception as e:
            # Attempt rollback
            self.state_manager.write_state(
                {
                    "phase": "error",
                    "error": str(e),
                    "attempting_rollback": True,
                }
            )
            # rollback_info should exist if we got past the rollback creation
            # If it doesn't, we can't rollback
            if rollback_info is not None:
                await self._perform_rollback(rollback_info)
                return {"success": False, "error": str(e), "rolled_back": True}
            return {"success": False, "error": str(e), "rolled_back": False}

        finally:
            self.state_manager.release_lock()

    async def _create_rollback_point(self) -> dict:
        """Create a rollback point before update.

        Returns:
            Dictionary with rollback information
        """
        rollback_dir = self.path_resolver.get_rollback_dir()

        # Save current git commit
        result = subprocess.run(
            ["git", "-C", str(self.app_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit = result.stdout.strip()

        # Backup configuration
        config_backup = rollback_dir / "config.yaml"
        shutil.copy2(
            self.path_resolver.get_birdnetpi_config_path(),
            config_backup,
        )

        # Backup database
        db_backup = rollback_dir / "birdnetpi.db"
        shutil.copy2(
            self.path_resolver.get_database_path(),
            db_backup,
        )

        return {
            "commit": commit,
            "config_backup": str(config_backup),
            "db_backup": str(db_backup),
            "created_at": datetime.now().isoformat(),
        }

    async def _perform_git_update(self, version: str) -> None:
        """Perform git update to specified version.

        Args:
            version: Target version tag
        """
        # Fetch latest changes
        subprocess.run(
            ["git", "-C", str(self.app_dir), "fetch", "--all", "--tags"],
            check=True,
        )

        # Checkout specific version
        subprocess.run(
            ["git", "-C", str(self.app_dir), "checkout", version],
            check=True,
        )

    async def _update_dependencies(self) -> None:
        """Update Python dependencies."""
        # Update dependencies using uv
        subprocess.run(
            ["uv", "sync"],
            cwd=str(self.app_dir),
            check=True,
        )

    async def _run_migrations(self) -> None:
        """Run database migrations using Alembic."""
        # Create Alembic config
        alembic_cfg = Config("alembic.ini")

        # Run migrations in thread pool (Alembic is sync)
        def run_upgrade() -> None:
            command.upgrade(alembic_cfg, "head")

        await asyncio.to_thread(run_upgrade)

    async def get_current_db_revision(self) -> str | None:
        """Get current database migration revision.

        Returns:
            Current Alembic revision or None if not initialized
        """

        def get_revision() -> str | None:
            # Get database path
            db_path = self.path_resolver.get_database_path()

            # If database doesn't exist, no migrations have been run
            if not db_path.exists():
                return None

            # Create engine and connect
            engine = create_engine(f"sqlite:///{db_path}")

            with engine.connect() as conn:
                # Check if alembic_version table exists
                result = conn.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='alembic_version'"
                    )
                )
                if not result.fetchone():
                    return None

                # Get the current revision
                result = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = result.fetchone()
                return str(row[0]) if row else None

        return await asyncio.to_thread(get_revision)

    async def rollback_migrations(self, target_revision: str) -> None:
        """Rollback database to a specific migration revision.

        Args:
            target_revision: Alembic revision to rollback to
        """
        alembic_cfg = Config("alembic.ini")

        def run_downgrade() -> None:
            command.downgrade(alembic_cfg, target_revision)

        await asyncio.to_thread(run_downgrade)

    async def _restart_services(self) -> None:
        """Restart all services after update."""
        # Use SystemControlService to restart services
        services = ["audio_capture", "audio_analysis", "audio_websocket", "fastapi"]
        for service in services:
            self.system_control.restart_service(service)

    async def _perform_rollback(self, rollback_info: dict) -> None:
        """Perform rollback to previous state.

        Args:
            rollback_info: Rollback information from create_rollback_point
        """
        try:
            # Restore git commit
            subprocess.run(
                ["git", "-C", str(self.app_dir), "reset", "--hard", rollback_info["commit"]],
                check=True,
            )

            # Restore configuration
            shutil.copy2(
                rollback_info["config_backup"],
                self.path_resolver.get_birdnetpi_config_path(),
            )

            # Restore database
            shutil.copy2(
                rollback_info["db_backup"],
                self.path_resolver.get_database_path(),
            )

            # Restart services
            await self._restart_services()

        except Exception as e:
            raise RuntimeError(f"Rollback failed: {e}") from e
