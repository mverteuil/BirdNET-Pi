import os
import subprocess


class LogManager:
    def __init__(self):
        self.home_dir = os.path.expanduser("~")

    def get_logs(self):
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
            sed_command = [
                "sed",
                r"s/{}/g;s/Line/d;/find/d;/systemd/d;s/ .*\[.*\]: /---/".format(
                    self.home_dir.replace("/", "\/")
                ),
            ]

            journalctl_process = subprocess.Popen(
                journalctl_command, stdout=subprocess.PIPE
            )
            sed_process = subprocess.Popen(
                sed_command, stdin=journalctl_process.stdout, stdout=subprocess.PIPE
            )

            # Allow journalctl_process to receive a SIGPIPE if sed_process exits.
            journalctl_process.stdout.close()

            output = sed_process.communicate()[0]
            return output.decode("utf-8")
        except FileNotFoundError:
            return "journalctl or sed not found. Please ensure they are installed and in your PATH."
