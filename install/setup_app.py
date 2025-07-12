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
        self.venv_path = self.file_path_resolver.get_absolute_path("birdnet")

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
        systemd_dir = "/etc/systemd/system/"
        user = "birdnetpi"  # Assuming 'birdnetpi' user is created by install.sh
        python_exec = os.path.join(self.venv_path, "bin", "python3")

        services = [
            {
                "name": "birdnet_analysis.service",
                "description": "BirdNET Analysis",
                "after": "birdnet_server.service",
                "requires": "birdnet_server.service",
                "exec_start": self.file_path_resolver.get_absolute_path("scripts/birdnet_analysis.sh"),
            },
            {
                "name": "birdnet_server.service",
                "description": "BirdNET Analysis Server",
                "before": "birdnet_analysis.service",
                "exec_start": f"{python_exec} {self.file_path_resolver.get_absolute_path('src/main.py')}", # Assuming main.py is the server entry
            },
            {
                "name": "extraction.service",
                "description": "BirdNET BirdSound Extraction",
                "exec_start": f"/usr/bin/env bash -c 'while true;do {self.file_path_resolver.get_absolute_path('scripts/extract_new_birdsounds.sh')};sleep 3;done'",
                "restart": "on-failure",
            },
            {
                "name": "birdnet_recording.service",
                "description": "BirdNET Recording",
                "exec_start": self.file_path_resolver.get_absolute_path("scripts/birdnet_recording.sh"),
                "environment": "XDG_RUNTIME_DIR=/run/user/1000",
            },
            {
                "name": "custom_recording.service",
                "description": "BirdNET Custom Recording",
                "exec_start": self.file_path_resolver.get_absolute_path("scripts/custom_recording.sh"),
                "environment": "XDG_RUNTIME_DIR=/run/user/1000",
            },
            {
                "name": "birdnet_stats.service",
                "description": "BirdNET Stats",
                "exec_start": f"{python_exec} -m streamlit run {self.file_path_resolver.get_absolute_path('src/reporting_dashboard.py')} --browser.gatherUsageStats false --server.address localhost --server.baseUrlPath \"/stats\"",
                "restart": "on-failure",
            },
            {
                "name": "spectrogram_viewer.service",
                "description": "BirdNET-Pi Spectrogram Viewer",
                "exec_start": self.file_path_resolver.get_absolute_path("scripts/spectrogram.sh"),
            },
            {
                "name": "chart_viewer.service",
                "description": "BirdNET-Pi Chart Viewer Service",
                "exec_start": f"{python_exec} {self.file_path_resolver.get_absolute_path('scripts/daily_plot.py')}", # Assuming daily_plot.py exists
            },
            {
                "name": "birdnet_log.service",
                "description": "BirdNET Analysis Log",
                "exec_start": f"/usr/local/bin/gotty --address localhost -p 8080 -P log --title-format \"BirdNET-Pi Log\" {self.file_path_resolver.get_absolute_path('scripts/birdnet_log.sh')}",
                "restart": "on-failure",
                "environment": "TERM=xterm-256color",
            },
            {
                "name": "web_terminal.service",
                "description": "BirdNET-Pi Web Terminal",
                "exec_start": "/usr/local/bin/gotty --address localhost -w -p 8888 -P terminal --title-format \"BirdNET-Pi Terminal\" login",
                "restart": "on-failure",
                "environment": "TERM=xterm-256color",
            },
            {
                "name": "livestream.service",
                "description": "BirdNET-Pi Live Stream",
                "exec_start": self.file_path_resolver.get_absolute_path("scripts/livestream.sh"),
                "after": "network-online.target",
                "requires": "network-online.target",
                "environment": "XDG_RUNTIME_DIR=/run/user/1000",
            },
        ]

        for service_config in services:
            service_name = service_config["name"]
            service_file_path = os.path.join(systemd_dir, service_name)
            content = f"[Unit]\nDescription={service_config['description']}\n"
            if "after" in service_config:
                content += f"After={service_config['after']}\n"
            if "before" in service_config:
                content += f"Before={service_config['before']}\n"
            if "requires" in service_config:
                content += f"Requires={service_config['requires']}\n"
            content += f"[Service]\nRestart=always\nType=simple\nUser={user}\n"
            if "restart" in service_config:
                content += f"Restart={service_config['restart']}\n"
            if "restart_sec" in service_config:
                content += f"RestartSec={service_config['restart_sec']}\n"
            if "environment" in service_config:
                content += f"Environment={service_config['environment']}\n"
            content += f"ExecStart={service_config['exec_start']}\n"
            content += "[Install]\nWantedBy=multi-user.target\n"

            # Write to a temporary file first
            temp_file_path = f"/tmp/{service_name}"
            with open(temp_file_path, "w") as f:
                f.write(content)

            # Move with sudo
            self._run_command(["sudo", "mv", temp_file_path, service_file_path], f"Creating {service_name}")
            self._run_command(["sudo", "systemctl", "enable", service_name], f"Enabling {service_name}")
            self._run_command(["sudo", "systemctl", "start", service_name], f"Starting {service_name}")

        self._run_command(["sudo", "systemctl", "daemon-reload"], "Reloading systemd daemon")
        print("Systemd services setup complete.")

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
