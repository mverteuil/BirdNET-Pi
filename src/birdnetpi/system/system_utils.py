import os
import subprocess


class SystemUtils:
    """Provides utility methods for interacting with the underlying operating system."""

    @staticmethod
    def get_system_timezone() -> str:
        """Attempt to determine the system's timezone."""
        try:
            # Try to get timezone from /etc/timezone
            with open("/etc/timezone") as f:
                tz_data = f.read().strip()
                if tz_data:
                    return tz_data
        except (FileNotFoundError, PermissionError, OSError):
            pass

        # Fallback to timedatectl
        try:
            result = subprocess.run(
                ["timedatectl", "show"], capture_output=True, text=True, check=True
            )
            for line in result.stdout.splitlines():
                if line.startswith("Timezone="):
                    return line.split("=")[1].strip()
        except Exception:
            pass

        return "UTC"  # Default to UTC if all else fails

    @staticmethod
    def is_docker_environment() -> bool:
        """Check if running in a Docker container."""
        return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

    @staticmethod
    def is_systemd_available() -> bool:
        """Check if systemd/journald is available on the system."""
        try:
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @staticmethod
    def get_git_version() -> str:
        """Get the current git branch and commit hash for version logging.

        Returns version in format: branch@SHA[:8]
        """
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get current commit hash (8 chars as requested)
            commit_result = subprocess.run(
                ["git", "rev-parse", "--short=8", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"

            return f"{branch}@{commit}"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return "unknown"

    @staticmethod
    def get_deployment_environment() -> str:
        """Get deployment environment with 'unknown' fallback."""
        if SystemUtils.is_docker_environment():
            return "docker"
        elif SystemUtils.is_systemd_available():
            return "sbc"
        elif os.environ.get("BIRDNETPI_ENV") == "development":
            return "development"
        else:
            return "unknown"
