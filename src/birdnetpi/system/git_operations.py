"""Git operations service for managing remotes and branches."""

import logging
import subprocess

from birdnetpi.system.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class GitRemote:
    """Represents a git remote with name and URL."""

    def __init__(self, name: str, url: str) -> None:
        """Initialize a GitRemote.

        Args:
            name: Remote name (e.g., 'origin')
            url: Remote URL
        """
        self.name = name
        self.url = url

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for API responses."""
        return {"name": self.name, "url": self.url}


class GitOperationsService:
    """Service for git operations including remote and branch management.

    This service provides operations for managing git remotes and querying
    branches/tags. It operates on the BirdNET-Pi repository.
    """

    def __init__(self, path_resolver: PathResolver) -> None:
        """Initialize GitOperationsService.

        Args:
            path_resolver: PathResolver instance for getting repository path
        """
        self.path_resolver = path_resolver
        self.repo_path = path_resolver.app_dir

    def _run_git_command(
        self, args: list[str], check: bool = True, capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command in the repository directory.

        Args:
            args: Git command arguments (e.g., ['remote', '-v'])
            check: Raise exception on non-zero exit code
            capture_output: Capture stdout/stderr

        Returns:
            CompletedProcess result

        Raises:
            subprocess.CalledProcessError: If check=True and command fails
        """
        cmd = ["git", "-C", str(self.repo_path), *args]
        logger.debug(f"Running git command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            timeout=30,
        )

        if result.returncode != 0 and not check:
            logger.warning(
                f"Git command failed (exit {result.returncode}): {result.stderr.strip()}"
            )

        return result

    def list_remotes(self) -> list[GitRemote]:
        """List all configured git remotes.

        Returns:
            List of GitRemote objects

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = self._run_git_command(["remote", "-v"])
        remotes = {}

        # Parse git remote -v output (each remote appears twice: fetch and push)
        # Example: origin  https://github.com/user/repo.git (fetch)
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                # Only store once per remote (ignore fetch/push distinction)
                if name not in remotes:
                    remotes[name] = GitRemote(name, url)

        return list(remotes.values())

    def get_remote_url(self, name: str) -> str | None:
        """Get the URL for a specific remote.

        Args:
            name: Remote name

        Returns:
            Remote URL or None if remote doesn't exist
        """
        result = self._run_git_command(
            ["remote", "get-url", name],
            check=False,
        )

        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def add_remote(self, name: str, url: str) -> None:
        """Add a new git remote.

        Args:
            name: Remote name
            url: Remote URL

        Raises:
            ValueError: If remote name already exists
            subprocess.CalledProcessError: If git command fails
        """
        # Check if remote already exists
        existing_url = self.get_remote_url(name)
        if existing_url is not None:
            raise ValueError(f"Remote '{name}' already exists with URL: {existing_url}")

        # Add the remote
        self._run_git_command(["remote", "add", name, url])
        logger.info(f"Added git remote '{name}' -> {url}")

    def update_remote(self, name: str, url: str) -> None:
        """Update the URL for an existing remote.

        Args:
            name: Remote name
            url: New remote URL

        Raises:
            ValueError: If remote doesn't exist
            subprocess.CalledProcessError: If git command fails
        """
        # Check if remote exists
        existing_url = self.get_remote_url(name)
        if existing_url is None:
            raise ValueError(f"Remote '{name}' does not exist")

        # Update the remote URL
        self._run_git_command(["remote", "set-url", name, url])
        logger.info(f"Updated git remote '{name}' from {existing_url} to {url}")

    def delete_remote(self, name: str) -> None:
        """Delete a git remote.

        Args:
            name: Remote name

        Raises:
            ValueError: If trying to delete 'origin' or remote doesn't exist
            subprocess.CalledProcessError: If git command fails
        """
        # Protect origin from deletion
        if name == "origin":
            raise ValueError("Cannot delete 'origin' remote")

        # Check if remote exists
        existing_url = self.get_remote_url(name)
        if existing_url is None:
            raise ValueError(f"Remote '{name}' does not exist")

        # Delete the remote
        self._run_git_command(["remote", "remove", name])
        logger.info(f"Deleted git remote '{name}' ({existing_url})")

    def fetch_remote(self, remote: str) -> None:
        """Fetch updates from a remote.

        Args:
            remote: Remote name to fetch from

        Raises:
            subprocess.CalledProcessError: If git fetch fails
        """
        logger.info(f"Fetching from remote '{remote}'...")
        self._run_git_command(["fetch", remote, "--tags"])
        logger.info(f"Successfully fetched from '{remote}'")

    def list_branches(self, remote: str) -> list[str]:
        """List branches available on a remote.

        Args:
            remote: Remote name

        Returns:
            List of branch names (without remote prefix)

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        # Use ls-remote to list branches without fetching
        # This is much faster than fetch + branch -r
        result = self._run_git_command(["ls-remote", "--heads", remote])

        branches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Parse ls-remote output: <hash><tab>refs/heads/<branch>
            parts = line.split("\t")
            if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                branch = parts[1].replace("refs/heads/", "")
                branches.append(branch)

        return sorted(branches)

    def list_tags(self, remote: str | None = None) -> list[str]:
        """List tags available (optionally from a remote).

        Args:
            remote: Remote name (if provided, queries remote directly)

        Returns:
            List of tag names (most recent first), excluding asset tags

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        if remote:
            # Use ls-remote to list tags without fetching
            result = self._run_git_command(["ls-remote", "--tags", remote])

            tags = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                # Parse ls-remote output: <hash><tab>refs/tags/<tag>
                parts = line.split("\t")
                if len(parts) == 2 and parts[1].startswith("refs/tags/"):
                    tag = parts[1].replace("refs/tags/", "")
                    # Skip ^{} (annotated tag references) and assets- prefixed tags
                    if not tag.endswith("^{}") and not tag.startswith("assets-"):
                        tags.append(tag)
        else:
            # List local tags
            result = self._run_git_command(["tag", "--list"])

            tags = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                # Filter out assets- prefixed tags
                if line and not line.startswith("assets-"):
                    tags.append(line)

        return sorted(tags, reverse=True)  # Most recent tags first

    def get_current_branch(self) -> str:
        """Get the name of the currently checked out branch.

        Returns:
            Current branch name

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()
