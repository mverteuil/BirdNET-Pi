import os
import shutil
import subprocess

from models.birdnet_config import BirdNETConfig
from services.file_manager import FileManager


class DataManager:
    def __init__(self, config: BirdNETConfig, file_manager: FileManager):
        self.config = config
        self.file_manager = file_manager

    def cleanup_processed_files(self):
        processed_dir = self.file_manager.get_processed_dir()

        for filename in os.listdir(processed_dir):
            if filename.endswith(".csv"):
                csv_path = os.path.join(processed_dir, filename)
                wav_path = os.path.join(processed_dir, filename.replace(".csv", ""))

                # Check if the csv file is empty (or very small)
                if os.path.getsize(csv_path) <= 57:
                    os.remove(csv_path)
                    if os.path.exists(wav_path):
                        os.remove(wav_path)

        # Limit the number of processed files to 100
        processed_files = sorted(
            os.listdir(processed_dir),
            key=lambda f: os.path.getmtime(os.path.join(processed_dir, f)),
            reverse=True,
        )

        if len(processed_files) > 100:
            files_to_delete = processed_files[100:]
            for f in files_to_delete:
                os.remove(os.path.join(processed_dir, f))

    def clear_all_data(self):
        print("Stopping services...")
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_recording.service"])
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_analysis.service"])
        subprocess.run(["sudo", "systemctl", "stop", "birdnet_server.service"])

        print("Removing all data...")
        shutil.rmtree(self.config.data.recordings_dir, ignore_errors=True)
        if os.path.exists(self.config.data.id_file):
            os.remove(self.config.data.id_file)
        if os.path.exists(self.config.data.bird_db_file):
            os.remove(self.config.data.bird_db_file)

        print("Re-creating necessary directories...")
        os.makedirs(self.config.data.extracted_dir, exist_ok=True)
        os.makedirs(os.path.join(self.config.data.extracted_dir, "By_Date"), exist_ok=True)
        os.makedirs(os.path.join(self.config.data.extracted_dir, "Charts"), exist_ok=True)
        os.makedirs(self.config.data.processed_dir, exist_ok=True)

        print("Re-establishing symlinks...")
        # Symlinks from original script, adjust paths as necessary
        # This part needs careful consideration of the new directory structure
        # and what symlinks are actually necessary for the Python implementation.
        # For now, I'll just put placeholders for the most critical ones.
        # More detailed symlink management might be handled by the installer.

        # Example: Symlink for BirdDB.txt
        if not os.path.exists(os.path.join(self.config.app_dir, "scripts", "BirdDB.txt")):
            with open(os.path.join(self.config.app_dir, "scripts", "BirdDB.txt"), "w") as f:
                f.write("Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap\n")
        os.symlink(os.path.join(self.config.app_dir, "scripts", "BirdDB.txt"), os.path.join(self.config.app_dir, "BirdDB.txt"))

        print("Restarting services...")
        subprocess.run(["sudo", "systemctl", "start", "birdnet_recording.service"])
        subprocess.run(["sudo", "systemctl", "start", "birdnet_analysis.service"])
        subprocess.run(["sudo", "systemctl", "start", "birdnet_server.service"])
