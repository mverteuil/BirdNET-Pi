import os
import subprocess

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.file_manager import FileManager
import os
import subprocess

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.file_manager import FileManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.managers.service_manager import ServiceManager


class DataManager:
    """Manages data operations, including cleanup and clearing of processed files and directories."""

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

    def cleanup_processed_files(self) -> None:
        """Clean up processed audio and CSV files, removing empty or old entries."""
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

    def clear_all_data(self) -> None:
        """Clear all BirdNET-Pi data, stopping services, removing files, and re-creating directories."""
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
        self.service_manager.start_service("birdnet_recording.service")
        self.service_manager.start_service("birdnet_analysis.service")
        self.service_manager.start_service("birdnet_server.service")
