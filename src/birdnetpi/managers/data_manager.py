import os
import shutil  # Import shutil

from birdnetpi.managers.service_manager import ServiceManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.file_manager import FileManager


class DataManager:
    """Manage data operations, including cleanup and clearing of processed files and directories."""

    def __init__(
        self,
        config: BirdNETConfig,
        file_manager: FileManager,
        db_service: DatabaseService,
        service_manager: ServiceManager,
    ) -> None:
        self.config = config
        self.file_manager = file_manager
        self.db_service = db_service
        self.service_manager = service_manager

    def get_recordings(self) -> list[str]:
        """Retrieve a list of recording file paths."""
        recordings_dir = self.file_manager.get_full_path(self.config.data.recordings_dir)
        return self.file_manager.list_directory_contents(recordings_dir)

    def cleanup_processed_files(self) -> None:
        """Clean up processed audio and CSV files, removing empty or old entries."""
        processed_dir = self.file_manager.get_full_path(self.config.data.processed_dir)

        for filename in self.file_manager.list_directory_contents(processed_dir):
            if filename.endswith(".csv"):
                csv_path = self.file_manager.get_full_path(os.path.join(processed_dir, filename))
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

    def clear_all_data(self) -> None:
        """Clear all BirdNET-Pi data, stop services, remove files, and re-create directories."""
        print("Stopping services...")
        self.service_manager.stop_service("birdnet_recording.service")
        self.service_manager.stop_service("birdnet_analysis.service")
        self.service_manager.stop_service("birdnet_server.service")

        print("Removing all data...")
        self.file_manager.delete_directory(self.config.data.recordings_dir)
        if self.file_manager.file_exists(self.config.data.id_file):
            self.file_manager.delete_file(self.config.data.id_file)

        # Clear the database instead of removing BirdDB.txt
        self.db_service.clear_database()

        print("Re-creating necessary directories...")
        self.file_manager.create_directory(self.config.data.extracted_dir)
        self.file_manager.create_directory(os.path.join(self.config.data.extracted_dir, "By_Date"))
        self.file_manager.create_directory(os.path.join(self.config.data.extracted_dir, "Charts"))
        self.file_manager.create_directory(self.config.data.processed_dir)

        print("Re-establishing symlinks...")
        # Define symlink targets and destinations
        symlinks = {
            self.config.data.recordings_dir: "/var/www/html/BirdSongs",
            self.config.data.processed_dir: "/var/www/html/Processed",
            self.config.data.extracted_dir: "/var/www/html/Extracted",
        }

        for target, link_name in symlinks.items():
            try:
                # Remove existing symlink or directory at link_name if it exists
                if os.path.islink(link_name):
                    os.unlink(link_name)
                elif os.path.isdir(link_name):
                    shutil.rmtree(link_name)

                # Create new symlink
                os.symlink(target, link_name)
                print(f"Created symlink: {link_name} -> {target}")
            except Exception as e:
                print(f"Error creating symlink {link_name} -> {target}: {e}")

        print("Restarting services...")
        self.service_manager.start_service("birdnet_recording.service")
        self.service_manager.start_service("birdnet_analysis.service")
        self.service_manager.start_service("birdnet_server.service")
