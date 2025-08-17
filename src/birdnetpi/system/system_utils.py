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
