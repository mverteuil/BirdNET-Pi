import os
import subprocess


class LogService:
    """Service for retrieving and processing system logs related to BirdNET-Pi services."""

    def __init__(self) -> None:
        self.home_dir = os.path.expanduser("~")

    def get_logs(self) -> str:
        """Retrieve and format BirdNET-Pi service logs using journalctl and sed."""
        try:
            journalctl_command = [
                "journalctl",
                "--no-hostname",
                "-q",
                "-o",
                "short",
                "-fu",
                "birdnet_analysis",
                "-u",
                "birdnet_server",
                "-u",
                "extraction",
            ]
            sed_pattern = r"s/{}/g;s/Line/d;/find/d;/systemd/d;s/ .*\[.*\]: /---/".format(
                self.home_dir.replace("/", r"\/")
            )
            sed_command = [
                "sed",
                sed_pattern,
            ]

            journalctl_process = subprocess.Popen(journalctl_command, stdout=subprocess.PIPE)
            sed_process = subprocess.Popen(
                sed_command, stdin=journalctl_process.stdout, stdout=subprocess.PIPE
            )

            # Allow journalctl_process to receive a SIGPIPE if sed_process exits.
            journalctl_process.stdout.close()

            output = sed_process.communicate()[0]
            return output.decode("utf-8")
        except FileNotFoundError:
            return "journalctl or sed not found. Please ensure they are installed and in your PATH."
