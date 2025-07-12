import os
import subprocess
import sys

# Add the src directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from models.birdnet_config import BirdNETConfig
from services.database_manager import DatabaseManager
from services.file_manager import FileManager
from utils.config_file_parser import ConfigFileParser
from utils.file_path_resolver import FilePathResolver


class AppSetup:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.file_path_resolver = FilePathResolver(repo_root)
        self.config_file_path = self.file_path_resolver.get_absolute_path(
            "etc/birdnet_pi_config.yaml"
        )
        self.config_parser = ConfigFileParser(self.config_file_path)
        self.config: BirdNETConfig = self.config_parser.parse()
        self.file_manager = FileManager(self.repo_root)
        self.database_manager = DatabaseManager(self.config.data.db_path)

    def _run_command(self, command: list[str], description: str):
        print(f"\n{description}...")
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"{description} complete.")
        except subprocess.CalledProcessError as e:
            print(f"Error during {description}: {e.stderr}")
            sys.exit(1)
        except Exception as e:
            print(f"An unexpected error occurred during {description}: {e}")
            sys.exit(1)

    def setup_virtual_environment(self):
        venv_path = self.file_path_resolver.get_absolute_path("birdnet")
        self._run_command(
            [sys.executable, "-m", "venv", venv_path],
            "Setting up Python virtual environment",
        )
        pip_path = os.path.join(venv_path, "bin", "pip")
        requirements_path = self.file_path_resolver.get_absolute_path(
            "requirements.txt"
        )
        self._run_command(
            [pip_path, "install", "-r", requirements_path],
            "Installing Python dependencies",
        )

    def create_directories(self):
        print("\nCreating necessary directories...")
        self.file_manager.create_directory(self.config.data.recordings_dir)
        self.file_manager.create_directory(self.config.data.extracted_dir)
        self.file_manager.create_directory(
            os.path.join(self.config.data.extracted_dir, "By_Date")
        )
        self.file_manager.create_directory(
            os.path.join(self.config.data.extracted_dir, "Charts")
        )
        self.file_manager.create_directory(self.config.data.processed_dir)
        print("Necessary directories created.")

    def initialize_database(self):
        print("\nInitializing database...")
        self.database_manager.initialize_database()
        print("Database initialized.")

    def setup_systemd_services(self):
        print("\nSetting up systemd services...")
        # This will involve creating .service files in /etc/systemd/system/
        # and enabling them. This is a placeholder for now.
        print("Systemd services setup complete (placeholder).")

    def run_setup(self):
        print("\nStarting BirdNET-Pi application setup...")
        self.setup_virtual_environment()
        self.create_directories()
        self.initialize_database()
        self.setup_systemd_services()
        print("BirdNET-Pi application setup complete.")


if __name__ == "__main__":
    # Assuming the script is run from the BirdNET-Pi directory or its parent
    # Determine repo_root dynamically
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))

    app_setup = AppSetup(repo_root)
    app_setup.run_setup()
