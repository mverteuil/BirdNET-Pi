"""Release management for BirdNET-Pi using orphaned commit strategy.

This module implements Ben Webber's orphaned commit strategy to distribute
large binary assets (models, IOC database) without bloating the main repository.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from birdnetpi.utils.file_path_resolver import FilePathResolver


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

    def __init__(self, file_resolver: FilePathResolver, repo_path: Path | None = None):
        """Initialize release manager.

        Args:
            file_resolver: File path resolver for asset locations
            repo_path: Path to git repository (defaults to current directory)
        """
        self.file_resolver = file_resolver
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
        """Create the orphaned commit with assets and tag it."""
        import tempfile

        # Create a temporary directory to preserve assets
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Copy assets to temp directory before cleaning
            print("Preserving assets in temporary location...")
            preserved_assets = []
            for asset in config.assets:
                source = asset.source_path
                if source.exists():
                    temp_target = temp_path / asset.target_name
                    temp_target.parent.mkdir(parents=True, exist_ok=True)

                    if source.is_file():
                        shutil.copy2(source, temp_target)
                    elif source.is_dir():
                        shutil.copytree(source, temp_target, dirs_exist_ok=True)

                    preserved_assets.append(
                        ReleaseAsset(temp_target, asset.target_name, asset.description)
                    )
                    print(f"  Preserved {asset.target_name}")

            # Create temporary orphaned branch
            temp_branch = f"temp-{config.asset_branch_name}"
            print(f"Creating temporary orphaned branch: {temp_branch}")
            self._run_git_command(["checkout", "--orphan", temp_branch])

            # Clean the orphaned branch
            self._run_git_command(["rm", "-rf", "."], check=False)
            self._run_git_command(["clean", "-fxd"], check=False)

            # Set up the orphaned branch
            self._create_asset_gitignore()
            self._copy_assets_to_branch(preserved_assets)
            self._create_asset_readme(config)

            # Commit the assets
            self._commit_assets(config)

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

    def _commit_assets(self, config: ReleaseConfig) -> None:
        """Add and commit only the assets to the orphaned branch."""
        for asset in config.assets:
            self._run_git_command(["add", str(asset.target_name)])
        self._run_git_command(["add", "README.md"])
        self._run_git_command(["add", ".gitignore"])
        self._run_git_command(["commit", "-m", config.commit_message, "--no-verify"])

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
        # In development, prefer local data/ directory over production paths
        models_path = self._get_asset_path("data/models", str(self.file_resolver.get_models_dir()))
        database_path = self._get_asset_path(
            "data/database/ioc_reference.db", str(self.file_resolver.get_ioc_database_path())
        )
        avibase_path = self._get_asset_path(
            "data/database/avibase_database.db", str(self.file_resolver.get_avibase_database_path())
        )
        patlevin_path = self._get_asset_path(
            "data/database/patlevin_database.db",
            str(self.file_resolver.get_patlevin_database_path()),
        )

        return [
            ReleaseAsset(
                source_path=models_path,
                target_name=Path("data/models"),
                description="BirdNET TensorFlow Lite models for bird identification",
            ),
            ReleaseAsset(
                source_path=database_path,
                target_name=Path("data/database/ioc_reference.db"),
                description="IOC World Bird Names reference database",
            ),
            ReleaseAsset(
                source_path=avibase_path,
                target_name=Path("data/database/avibase_database.db"),
                description="Avibase multilingual bird names database (Lepage 2018, CC-BY-4.0)",
            ),
            ReleaseAsset(
                source_path=patlevin_path,
                target_name=Path("data/database/patlevin_database.db"),
                description="BirdNET label translations compiled by Patrick Levin",
            ),
        ]

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

This branch contains binary assets for BirdNET-Pi version {config.version}.

## Assets Included

"""
        for asset in config.assets:
            readme_content += f"- **{asset.target_name}**: {asset.description}\n"

        readme_content += f"""
## Installation

These assets are automatically downloaded during BirdNET-Pi installation.
For manual installation:

1. Clone the main BirdNET-Pi repository
2. Download assets from this tagged release
3. Place assets in the appropriate directories as specified in the documentation

## Technical Details

This release uses the orphaned commit strategy to distribute large binary files
without bloating the main repository history. Credit to Ben Webber for this approach.

- **Release Version**: {config.version}
- **Asset Tag**: {config.asset_branch_name}
- **Created**: Automated release system
"""

        readme_path = self.repo_path / "README.md"
        readme_path.write_text(readme_content)

    def _generate_release_notes(self, config: ReleaseConfig, asset_commit_sha: str) -> str:
        """Generate release notes for GitHub release."""
        notes = f"""## BirdNET-Pi {config.version}

### Binary Assets

This release includes the following binary assets distributed via orphaned commit:

"""
        for asset in config.assets:
            notes += f"- **{asset.target_name}**: {asset.description}\n"

        notes += f"""
### Asset Download

Binary assets are available from the orphaned commit tagged as `{config.asset_branch_name}`
[{asset_commit_sha[:8]}](../../commit/{asset_commit_sha})
and can be downloaded automatically during installation.

### Technical Details

- **Asset Tag**: `{config.asset_branch_name}`
- **Asset Commit**: `{asset_commit_sha}`
- **Distribution Strategy**: Orphaned commits with tags (credit: Ben Webber)

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
