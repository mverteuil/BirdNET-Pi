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
        # First fetch to ensure we have latest refs
        try:
            self.fetch_remote(remote)
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to fetch remote '{remote}': {e}")
            # Continue anyway, use cached refs

        # List remote branches
        result = self._run_git_command(["branch", "-r", "--list", f"{remote}/*"])

        branches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Remove leading/trailing whitespace and remote prefix
            branch = line.strip()
            # Remove 'origin/' prefix
            if branch.startswith(f"{remote}/"):
                branch = branch[len(remote) + 1 :]
            # Skip HEAD pointer
            if "HEAD" not in branch:
                branches.append(branch)

        return sorted(branches)

    def list_tags(self, remote: str | None = None) -> list[str]:
        """List tags available (optionally from a remote).

        Args:
            remote: Remote name (if provided, fetches first)

        Returns:
            List of tag names

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        # Fetch from remote if specified
        if remote:
            try:
                self.fetch_remote(remote)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to fetch remote '{remote}': {e}")
                # Continue anyway, use cached tags

        # List all tags
        result = self._run_git_command(["tag", "--list"])

        tags = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
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
