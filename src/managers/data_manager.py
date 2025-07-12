import os
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
