"""Release management for BirdNET-Pi using orphaned commit strategy.

This module implements Ben Webber's orphaned commit strategy to distribute
large binary assets (models, IOC database) without bloating the main repository.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from birdnetpi.releases.asset_manifest import AssetManifest
from birdnetpi.system.path_resolver import PathResolver


@dataclass
class ReleaseAsset:
    """Represents a release asset to be included in orphaned commit."""

    source_path: Path
    target_name: Path
    description: str


@dataclass
class ReleaseConfig:
    """Configuration for a release."""

    version: str
    asset_branch_name: str
    commit_message: str
    assets: list[ReleaseAsset]
    tag_name: str | None = None


class ReleaseManager:
    """Manages creation of releases using orphaned commit strategy."""

    def __init__(self, path_resolver: PathResolver, repo_path: Path | None = None):
        """Initialize release manager.

        Args:
            path_resolver: File path resolver for asset locations
            repo_path: Path to git repository (defaults to current directory)
        """
        self.path_resolver = path_resolver
        self.repo_path = repo_path or Path.cwd()

    def create_asset_release(self, config: ReleaseConfig) -> dict[str, Any]:
        """Create an orphaned commit with release assets.

        Args:
            config: Release configuration

        Returns:
            Dictionary with release information including commit SHA
        """
        print(f"Creating asset release for version {config.version}")
        self._validate_assets_exist(config.assets)

        original_branch = self._get_current_branch()
        commit_sha = None

        try:
            commit_sha = self._create_orphaned_commit(config)
        finally:
            self._cleanup_and_return_to_branch(original_branch)

        return self._build_release_info(config, commit_sha)

    def _validate_assets_exist(self, assets: list[ReleaseAsset]) -> None:
        """Validate that all assets exist before creating release."""
        missing_assets = []
        for asset in assets:
            if not asset.source_path.exists():
                missing_assets.append(asset.source_path)

        if missing_assets:
            raise FileNotFoundError(f"Missing assets: {missing_assets}")

    def _create_orphaned_commit(self, config: ReleaseConfig) -> str:
        """Create the orphaned commit with README only, then upload gzipped assets."""
        import tempfile

        # Create a temporary directory for gzipped assets
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # IMPORTANT: Preserve assets BEFORE creating orphaned branch
            # (we lose access to working directory files after checkout --orphan)
            print("Preserving assets before branch creation...")
            preserved_assets = []
            for asset in config.assets:
                source = asset.source_path
                if source.exists():
                    temp_asset = temp_path / "sources" / asset.target_name
                    temp_asset.parent.mkdir(parents=True, exist_ok=True)

                    if source.is_file():
                        shutil.copy2(source, temp_asset)
                    elif source.is_dir():
                        shutil.copytree(source, temp_asset, dirs_exist_ok=True)

                    preserved_assets.append(
                        ReleaseAsset(temp_asset, asset.target_name, asset.description)
                    )
                    print(f"  Preserved {asset.target_name}")

            # Create temporary orphaned branch
            temp_branch = f"temp-{config.asset_branch_name}"
            print(f"Creating temporary orphaned branch: {temp_branch}")
            self._run_git_command(["checkout", "--orphan", temp_branch])

            # Clean the orphaned branch
            self._run_git_command(["rm", "-rf", "."], check=False)
            self._run_git_command(["clean", "-fxd"], check=False)

            # Set up the orphaned branch with ONLY README (no asset files)
            self._create_asset_gitignore()
            self._create_asset_readme(config)

            # Commit only README and .gitignore
            self._commit_readme_only(config)

            # Get commit SHA
            commit_sha = self._run_git_command(["rev-parse", "HEAD"], capture_output=True).strip()
            print(f"Created orphaned commit: {commit_sha}")

            # Tag the orphaned commit
            tag_name = config.asset_branch_name  # This will be assets-v1.0.0
            print(f"Tagging orphaned commit as: {tag_name}")
            self._run_git_command(["tag", "-a", tag_name, "-m", f"Asset release {config.version}"])

            # Push the tag (not the branch)
            print(f"Pushing tag: {tag_name}")
            self._run_git_command(["push", "origin", tag_name])

            # Create GitHub release for the asset tag
            print(f"Creating GitHub release for {tag_name}")
            release_notes = self._generate_release_notes(config, commit_sha)
            try:
                subprocess.run(
                    [
                        "gh",
                        "release",
                        "create",
                        tag_name,
                        "--title",
                        f"Assets Release {config.version}",
                        "--notes",
                        release_notes,
                        "--target",
                        commit_sha,
                    ],
                    check=True,
                )
                print(f"GitHub release created: {tag_name}")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to create GitHub release: {e}")
                print(
                    "The tag was created successfully, but you may need to "
                    "create the release manually"
                )

            # Gzip and upload assets to the release using preserved copies
            print("\nGzipping and uploading assets to release...")
            self._upload_gzipped_assets(
                ReleaseConfig(
                    version=config.version,
                    asset_branch_name=config.asset_branch_name,
                    commit_message=config.commit_message,
                    assets=preserved_assets,
                    tag_name=config.tag_name,
                ),
                tag_name,
                temp_path,
            )

            return commit_sha

    def _copy_assets_to_branch(self, assets: list[ReleaseAsset]) -> None:
        """Copy assets to the orphaned branch."""
        print("Copying assets...")
        for asset in assets:
            source = asset.source_path
            target = self.repo_path / asset.target_name

            if source.is_file():
                # Ensure parent directory exists
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                print(f"  Copied {source} -> {asset.target_name}")
            elif source.is_dir():
                # Ensure parent directory exists
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target, dirs_exist_ok=True)
                print(f"  Copied directory {source} -> {asset.target_name}")

    def _commit_readme_only(self, config: ReleaseConfig) -> None:
        """Add and commit only README and .gitignore to the orphaned branch."""
        self._run_git_command(["add", "README.md"])
        self._run_git_command(["add", ".gitignore"])
        self._run_git_command(["commit", "-m", config.commit_message, "--no-verify"])

    def _upload_gzipped_assets(self, config: ReleaseConfig, tag_name: str, temp_dir: Path) -> None:
        """Gzip assets and upload them to the GitHub release."""
        import gzip

        upload_args = ["gh", "release", "upload", tag_name]

        for asset in config.assets:
            source = asset.source_path
            if not source.exists():
                print(f"Warning: Asset not found: {source}")
                continue

            if source.is_file():
                # Gzip the file
                gzipped_path = temp_dir / f"{asset.target_name.name}.gz"
                print(f"  Gzipping {asset.target_name}...")

                with open(source, "rb") as f_in:
                    with gzip.open(gzipped_path, "wb", compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Add to upload args
                upload_args.append(str(gzipped_path))
                print(f"  Queued for upload: {gzipped_path.name}")

            elif source.is_dir():
                # For directories, create a tar.gz
                import tarfile

                tarball_path = temp_dir / f"{asset.target_name.name}.tar.gz"
                print(f"  Creating tarball {tarball_path.name}...")

                with tarfile.open(tarball_path, "w:gz", compresslevel=9) as tar:
                    tar.add(source, arcname=asset.target_name.name)

                # Add to upload args
                upload_args.append(str(tarball_path))
                print(f"  Queued for upload: {tarball_path.name}")

        # Upload all assets in one command
        if len(upload_args) > 3:  # More than just gh release upload tag_name
            print("\nUploading assets to GitHub release...")
            try:
                subprocess.run(upload_args, check=True, cwd=self.repo_path)
                print("All assets uploaded successfully!")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to upload assets: {e}")
                print("You may need to upload them manually")
        else:
            print("No assets to upload")

    def _cleanup_and_return_to_branch(self, original_branch: str) -> None:
        """Return to original branch with proper cleanup."""
        if original_branch:
            print(f"Returning to original branch: {original_branch}")
            try:
                self._run_git_command(["checkout", original_branch])

                # Delete the temporary orphaned branch
                temp_branches = [
                    branch.strip().replace("* ", "").replace("  ", "")
                    for branch in self._run_git_command(["branch"], capture_output=True).split("\n")
                    if branch.strip().startswith("temp-assets-")
                ]

                for temp_branch in temp_branches:
                    if temp_branch:
                        print(f"Deleting temporary branch: {temp_branch}")
                        self._run_git_command(["branch", "-D", temp_branch], check=False)

            except subprocess.CalledProcessError:
                print("Checkout failed, cleaning up uncommitted changes...")
                try:
                    self._run_git_command(["reset", "--hard"], check=False)
                    self._run_git_command(["clean", "-fxd"], check=False)
                    self._run_git_command(["checkout", original_branch])
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Could not return to original branch {original_branch}: {e}")
                    print("You may need to manually checkout the correct branch")

    def _build_release_info(self, config: ReleaseConfig, commit_sha: str) -> dict[str, Any]:
        """Build the release information dictionary."""
        return {
            "version": config.version,
            "asset_branch": config.asset_branch_name,  # Kept for backward compatibility
            "asset_tag": config.asset_branch_name,  # Now refers to tag, not branch
            "commit_sha": commit_sha,
            "assets": [
                {
                    "name": str(asset.target_name),
                    "description": asset.description,
                    "source": str(asset.source_path),
                }
                for asset in config.assets
            ],
        }

    def create_github_release(self, config: ReleaseConfig, asset_commit_sha: str) -> dict[str, Any]:
        """Create a GitHub release referencing the asset commit.

        Args:
            config: Release configuration
            asset_commit_sha: SHA of the orphaned commit with assets

        Returns:
            Dictionary with GitHub release information
        """
        tag_name = config.tag_name or f"v{config.version}"

        # Create release notes
        release_notes = self._generate_release_notes(config, asset_commit_sha)

        print(f"Creating GitHub release: {tag_name}")

        # Use GitHub CLI to create release
        gh_command = [
            "gh",
            "release",
            "create",
            tag_name,
            "--title",
            f"BirdNET-Pi {config.version}",
            "--notes",
            release_notes,
        ]

        result = self._run_command(gh_command, capture_output=True)
        print(f"GitHub release created: {tag_name}")

        return {
            "tag_name": tag_name,
            "release_url": result.strip() if result else None,
            "asset_commit_sha": asset_commit_sha,
        }

    def get_default_assets(self) -> list[ReleaseAsset]:
        """Get the default list of assets for a BirdNET-Pi release.

        Returns:
            List of default release assets
        """
        # Use AssetManifest to get all release assets
        asset_tuples = AssetManifest.get_release_assets(self.path_resolver)

        release_assets = []
        for source_path, target_path, description in asset_tuples:
            # In development, prefer local data/ directory over production paths
            actual_source = self._get_asset_path(str(target_path), str(source_path))

            release_assets.append(
                ReleaseAsset(
                    source_path=actual_source,
                    target_name=target_path,
                    description=description,
                )
            )

        return release_assets

    def _get_asset_path(self, dev_path: str, prod_path: str) -> Path:
        """Get asset path, preferring development path over production path.

        Args:
            dev_path: Development environment path (relative to repo root)
            prod_path: Production environment path

        Returns:
            Path to use for the asset
        """
        dev_full_path = self.repo_path / dev_path
        if dev_full_path.exists():
            return dev_full_path
        return Path(prod_path)

    def _create_asset_gitignore(self) -> None:
        """Create a minimal .gitignore file for the asset branch.

        This .gitignore excludes common system files but specifically
        allows the data/ directory to be committed to the orphaned branch.
        """
        gitignore_content = """# System files
.DS_Store
Thumbs.db
.Spotlight-V100
.Trashes
ehthumbs.db
Desktop.ini

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.env
.venv

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Logs
*.log

# Temporary files
*.tmp
*.temp

# Git
.git/

# NOTE: data/ directory is NOT excluded - it contains the assets for this release
"""
        gitignore_path = self.repo_path / ".gitignore"
        gitignore_path.write_text(gitignore_content)

    def _get_current_branch(self) -> str:
        """Get the current git branch name."""
        try:
            return self._run_git_command(["branch", "--show-current"], capture_output=True).strip()
        except subprocess.CalledProcessError:
            return "main"  # fallback

    def _create_asset_readme(self, config: ReleaseConfig) -> None:
        """Create a README file for the asset branch."""
        readme_content = f"""# BirdNET-Pi Release Assets - {config.version}

This orphaned commit provides a lightweight tag for BirdNET-Pi asset release {config.version}.

## Assets Available as Downloads

All binary assets are attached to this release as gzipped downloads to minimize repository size.

"""
        for asset in config.assets:
            # Determine the download filename
            if asset.source_path.is_dir():
                download_name = f"{asset.target_name.name}.tar.gz"
            else:
                download_name = f"{asset.target_name.name}.gz"
            readme_content += f"- **{download_name}**: {asset.description}\n"

        readme_content += f"""

## Installation

These assets are automatically downloaded and decompressed during BirdNET-Pi installation.

For manual installation:

1. Download the gzipped asset files from this release's downloads
2. Decompress them: `gunzip <filename>.gz` or `tar xzf <filename>.tar.gz`
3. Place assets in the appropriate directories as specified in the documentation

## Technical Details

This release uses the orphaned commit strategy with external asset storage:
- The orphaned commit contains only this README (keeping it tiny)
- Binary assets are attached as gzipped release downloads
- Downloads are automatically decompressed during installation

Credit to Ben Webber for the orphaned commit approach.

- **Release Version**: {config.version}
- **Asset Tag**: {config.asset_branch_name}
- **Created**: Automated release system
- **Compression**: gzip (level 9)
"""
        readme_path = self.repo_path / "README.md"
        readme_path.write_text(readme_content)

    def _generate_release_notes(self, config: ReleaseConfig, asset_commit_sha: str) -> str:
        """Generate release notes for GitHub release."""
        notes = f"""## BirdNET-Pi Assets Release {config.version}

### Binary Assets (Gzipped Downloads)

This release includes the following binary assets as gzipped downloads attached to this release:

"""
        for asset in config.assets:
            # Determine the download filename
            if asset.source_path.is_dir():
                download_name = f"{asset.target_name.name}.tar.gz"
            else:
                download_name = f"{asset.target_name.name}.gz"
            notes += f"- **{download_name}**: {asset.description}\n"

        notes += f"""

### Download and Installation

Binary assets are attached to this release as gzipped downloads. The orphaned
commit [{asset_commit_sha[:8]}](../../commit/{asset_commit_sha}) contains only
a README to keep the tag lightweight.

Assets are automatically downloaded and decompressed during BirdNET-Pi installation
using the `install-assets` CLI tool.

### Technical Details

- **Asset Tag**: `{config.asset_branch_name}`
- **Asset Commit**: `{asset_commit_sha}` (README only)
- **Distribution Strategy**: Orphaned commits with external gzipped assets
- **Compression**: gzip level 9
- **Benefits**:
  - Tiny orphaned commit (just README)
  - Efficient compression reduces download size
  - Automatic decompression during installation

Credit to Ben Webber for the orphaned commit approach.

For installation instructions, see the main repository README.
"""
        return notes

    def _run_git_command(
        self, args: list[str], capture_output: bool = False, check: bool = True
    ) -> str:
        """Run a git command in the repository directory."""
        return self._run_command(["git", *args], capture_output=capture_output, check=check)

    def _run_command(
        self, args: list[str], capture_output: bool = False, check: bool = True
    ) -> str:
        """Run a command with proper error handling."""
        try:
            result = subprocess.run(
                args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=check,
            )
            if result.returncode != 0 and check:
                print(f"Command failed: {' '.join(args)}")
                print(f"Exit code: {result.returncode}")
                print(f"Stdout: {result.stdout}")
                print(f"Stderr: {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, args, result.stdout, result.stderr
                )
            return result.stdout if capture_output else ""
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {' '.join(args)}")
            print(f"Error output: {e.stderr}")
            raise
