import os
import re
import subprocess


class UpdateManager:
    """Manages updates and Git operations for the BirdNET-Pi repository."""

    def __init__(self) -> None:
        script_dir = os.path.dirname(__file__)
        self.repo_path = os.path.abspath(os.path.join(script_dir, "..", ".."))

    def get_commits_behind(self) -> int:
        """Check how many commits the local repository is behind the remote."""
        try:
            # Git fetch to update remote tracking branches
            subprocess.run(
                ["git", "-C", self.repo_path, "fetch"], check=True, capture_output=True
            )

            # Git status to get the status of the repository
            result = subprocess.run(
                ["git", "-C", self.repo_path, "status"],
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
            match_diverged = re.search(
                r"(\d+) and (\d+) different commits each", status_output
            )
            if match_diverged:
                return int(match_diverged.group(1)) + int(match_diverged.group(2))

            return 0  # No commits behind
        except subprocess.CalledProcessError as e:
            print(f"Error executing git command: {e.stderr}")
            return -1  # Indicate an error
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return -1  # Indicate an error

    def update_birdnet(self, remote: str = "origin", branch: str = "main") -> None:
        """Update the BirdNET-Pi repository to the latest version."""
        try:
            # Get current HEAD hash
            current_commit_hash = subprocess.run(
                ["git", "-C", self.repo_path, "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Reset current HEAD to remove any local changes
            subprocess.run(
                ["git", "-C", self.repo_path, "reset", "--hard"],
                check=True,
                capture_output=True,
            )

            # Fetches latest changes
            subprocess.run(
                ["git", "-C", self.repo_path, "fetch", remote, branch],
                check=True,
                capture_output=True,
            )

            # Switches git to specified branch
            subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo_path,
                    "switch",
                    "-C",
                    branch,
                    "--track",
                    f"{remote}/{branch}",
                ],
                check=True,
                capture_output=True,
            )

            # Prints out changes
            diff_output = subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo_path,
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
            script_dir = os.path.join(self.repo_path, "scripts")
            for script in os.listdir(script_dir):
                if os.path.isfile(os.path.join(script_dir, script)):
                    subprocess.run(
                        [
                            "sudo",
                            "ln",
                            "-sf",
                            os.path.join(script_dir, script),
                            "/usr/local/bin/",
                        ],
                        check=True,
                    )

            # Call update_birdnet_snippets (assuming it's also a Python function now)
            # This will be handled by the wrapper script calling the appropriate Python function
            print("Calling update_birdnet_snippets...")

        except subprocess.CalledProcessError as e:
            print(f"Error during BirdNET-Pi update: {e.stderr}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during update: {e}")
            raise

    def update_caddyfile(
        self, birdnetpi_url: str, extracted_path: str, caddy_pwd: str | None = None
    ) -> None:
        """Update the Caddyfile with new configuration and reload Caddy."""
        try:
            # Ensure /etc/caddy exists
            subprocess.run(["sudo", "mkdir", "-p", "/etc/caddy"], check=True)

            caddyfile_path = "/etc/caddy/Caddyfile"

            # Backup existing Caddyfile if it exists
            if os.path.exists(caddyfile_path):
                subprocess.run(
                    ["sudo", "cp", caddyfile_path, f"{caddyfile_path}.original"],
                    check=True,
                )

            caddyfile_content = (
                f"http:// {birdnetpi_url} {{\n"
                "  reverse_proxy localhost:8000\n"
                "  reverse_proxy /log* localhost:8080\n"
                "  reverse_proxy /stats* localhost:8501\n"
                "  reverse_proxy /terminal* localhost:8888\n"
                "}\n"
            )

            # Write the Caddyfile content
            # Using a temporary file and then moving it with sudo to handle permissions
            temp_caddyfile_path = "/tmp/Caddyfile_temp"
            with open(temp_caddyfile_path, "w") as f:
                f.write(caddyfile_content)
            subprocess.run(
                ["sudo", "mv", temp_caddyfile_path, caddyfile_path], check=True
            )

            # Format and reload Caddy
            subprocess.run(
                ["sudo", "caddy", "fmt", "--overwrite", caddyfile_path], check=True
            )
            subprocess.run(["sudo", "systemctl", "reload", "caddy"], check=True)

            print("Caddyfile updated and Caddy reloaded successfully.")

        except subprocess.CalledProcessError as e:
            print(f"Error updating Caddyfile: {e.stderr}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during Caddyfile update: {e}")
            raise
