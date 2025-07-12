import re
import subprocess


class UpdateManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def get_commits_behind(self) -> int:
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
