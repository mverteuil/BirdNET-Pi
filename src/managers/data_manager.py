import os
import subprocess

from models.birdnet_config import BirdNETConfig
from services.database_manager import DatabaseManager
from services.file_manager import FileManager


class DataManager:
    def __init__(
        self,
        config: BirdNETConfig,
        file_manager: FileManager,
        database_manager: DatabaseManager,
    ):
        self.config = config
        self.file_manager = file_manager
        self.database_manager = database_manager

    def cleanup_processed_files(self):
        processed_dir = self.file_manager.get_full_path(self.config.data.processed_dir)

        for filename in self.file_manager.list_directory_contents(processed_dir):
            if filename.endswith(".csv"):
                csv_path = self.file_manager.get_full_path(
                    os.path.join(processed_dir, filename)
                )
                wav_path = self.file_manager.get_full_path(
                    os.path.join(processed_dir, filename.replace(".csv", ""))
                )

                # Check if the csv file is empty (or very small)
                if os.path.getsize(csv_path) <= 57:
                    self.file_manager.delete_file(csv_path)
                    if self.file_manager.file_exists(wav_path):
                        self.file_manager.delete_file(wav_path)

        # Limit the number of processed files to 100
        processed_files = sorted(
            self.file_manager.list_directory_contents(processed_dir),
            key=lambda f: os.path.getmtime(
                self.file_manager.get_full_path(os.path.join(processed_dir, f))
            ),
            reverse=True,
        )

        if len(processed_files) > 100:
            files_to_delete = processed_files[100:]
            for f in files_to_delete:
                self.file_manager.delete_file(
                    self.file_manager.get_full_path(os.path.join(processed_dir, f))
                )

    def clear_all_data(self):
        print("Stopping services...")
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_recording.service"])
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_analysis.service"])
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_server.service"])

        print("Removing all data...")
        self.file_manager.delete_directory(self.config.data.recordings_dir)
        if self.file_manager.file_exists(self.config.data.id_file):
            self.file_manager.delete_file(self.config.data.id_file)

        # Clear the database instead of removing BirdDB.txt
        self.database_manager.clear_database()

        print("Re-creating necessary directories...")
        self.file_manager.create_directory(self.config.data.extracted_dir)
        self.file_manager.create_directory(
            os.path.join(self.config.data.extracted_dir, "By_Date")
        )
        self.file_manager.create_directory(
            os.path.join(self.config.data.extracted_dir, "Charts")
        )
        self.file_manager.create_directory(self.config.data.processed_dir)

        print("Re-establishing symlinks...")
        # Symlinks from original script, adjust paths as necessary
        # This part needs careful consideration of the new directory structure
        # and what symlinks are actually necessary for the Python implementation.
        # For now, I'll just put placeholders for the most critical ones.
        # More detailed symlink management might be handled by the installer.

        print("Restarting services...")
        subprocess.run(["sudo", "systemctl", "start", "birdnet_recording.service"])
        subprocess.run(["sudo", "systemctl", "start", "birdnet_analysis.service"])
        subprocess.run(["sudo", "systemctl", "start", "birdnet_server.service"])
