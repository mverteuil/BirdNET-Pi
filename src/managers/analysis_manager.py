import os
import subprocess

from models.birdnet_config import BirdNETConfig
from services.database_manager import DatabaseManager
from services.file_manager import FileManager


class AnalysisManager:
    def __init__(
        self,
        config: BirdNETConfig,
        db_manager: DatabaseManager,
        file_manager: FileManager,
    ):
        self.config = config
        self.db_manager = db_manager
        self.file_manager = file_manager

    def run_analysis(self, file_path):
        python_executable = os.path.join(
            self.config.app_dir, "birdnet", "bin", "python3"
        )
        analysis_script = os.path.join(self.config.app_dir, "scripts", "analyze.py")

        command = [
            python_executable,
            analysis_script,
            "--i",
            file_path,
            "--o",
            file_path + ".csv",
            "--lat",
            str(self.config.latitude),
            "--lon",
            str(self.config.longitude),
            "--week",
            str(self.config.week_of_year),
            "--overlap",
            str(self.config.overlap),
            "--sensitivity",
            str(self.config.sensitivity),
            "--min_conf",
            str(self.config.min_confidence),
        ]

        # Add include and exclude lists if they exist
        if self.config.include_list and os.path.exists(self.config.include_list):
            command.extend(["--include_list", self.config.include_list])
        if self.config.exclude_list and os.path.exists(self.config.exclude_list):
            command.extend(["--exclude_list", self.config.exclude_list])

        # Add BirdWeather ID if it exists
        if self.config.birdweather_id:
            command.extend(["--birdweather_id", self.config.birdweather_id])

        subprocess.run(command)

    def process_recordings(self):
        recording_dir = self.file_manager.get_recording_dir()
        analyzed_dir = os.path.join(recording_dir, "Analyzed")

        # Create the Analyzed directory if it doesn't exist
        if not os.path.exists(analyzed_dir):
            os.makedirs(analyzed_dir)

        # Get a list of audio files to analyze
        files_to_analyze = sorted(
            [
                f
                for f in os.listdir(recording_dir)
                if f.endswith(".wav")
                and os.path.getsize(os.path.join(recording_dir, f)) > 0
            ]
        )[:20]

        # Move already analyzed files
        for file in files_to_analyze[:]:
            csv_file = file + ".csv"
            if os.path.exists(os.path.join(recording_dir, csv_file)):
                os.rename(
                    os.path.join(recording_dir, file), os.path.join(analyzed_dir, file)
                )
                os.rename(
                    os.path.join(recording_dir, csv_file),
                    os.path.join(analyzed_dir, csv_file),
                )
                files_to_analyze.remove(file)

        # Run analysis on the remaining files
        for file in files_to_analyze:
            self.run_analysis(os.path.join(recording_dir, file))
