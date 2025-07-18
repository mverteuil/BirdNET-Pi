from datetime import datetime, timedelta  # Import timedelta

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection  # Import Detection model
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager
import subprocess  # Import subprocess for calling sox
import os # Import os for path manipulation


class AnalysisManager:
    """Manages the analysis of audio files, storing results, and publishing detection events."""

    def __init__(
        self,
        config: BirdNETConfig,
        file_manager: FileManager,
        detection_manager: DetectionManager,
        analysis_client_service: AnalysisClientService,
        detection_event_publisher: DetectionEventPublisher,
    ) -> None:
        self.config = config
        self.file_manager = file_manager
        self.detection_manager = detection_manager
        self.analysis_client_service = analysis_client_service
        self.detection_event_publisher = detection_event_publisher

    def process_audio_for_analysis(self, audio_file_path: str) -> None:
        """Process an audio file for analysis, store results, and publish events."""
        print(f"Processing audio for analysis: {audio_file_path}")
        # 1. Send to analysis client
        analysis_results = self.analysis_client_service.analyze_audio(audio_file_path)

        # 2. Store in database
        if analysis_results:
            for result in analysis_results:
                # Assuming result is a dict with 'species', 'confidence', 'timestamp'
                # Convert timestamp string to datetime object if necessary
                timestamp_dt = (
                    datetime.fromisoformat(result["timestamp"])
                    if isinstance(result["timestamp"], str)
                    else result["timestamp"]
                )

                detection = Detection(
                    species=result["species"],
                    confidence=result["confidence"],
                    timestamp=timestamp_dt,
                    audio_file_path=audio_file_path,
                    # Add other fields from analysis_results if available and relevant
                )
                new_detection = self.detection_manager.add_detection(detection)
                print(f"Added detection to DB: {new_detection.species}")

                # 3. Publish detection event
                self.detection_event_publisher.publish_detection(new_detection)

    def extract_new_birdsounds(self) -> None:
        """Extract new birdsounds based on analysis results."""
        print("Extracting new birdsounds...")
        detections_to_extract = self.detection_manager.get_all_detections() # For simplicity, process all

        extracted_dir = self.file_manager.get_full_path(self.config.data.extracted_dir)
        extracted_dir.mkdir(parents=True, exist_ok=True)

        for detection in detections_to_extract:
            input_audio_path = self.file_manager.get_full_path(detection.audio_file_path)
            audio_file = self.detection_manager.get_audio_file_by_path(detection.audio_file_path)

            if not audio_file:
                sys.stderr.write(f"Error: AudioFile record not found for {detection.audio_file_path}. Skipping extraction.\n")
                continue
            
            # Calculate start time and duration for extraction
            extraction_length = float(self.config.extraction_length) if self.config.extraction_length else 6.0
            
            # Calculate the start time for sox trim based on recording_start_time
            time_difference = detection.timestamp - audio_file.recording_start_time
            start_time_seconds = time_difference.total_seconds()
            
            output_filename = f"{detection.species.replace(' ', '_')}_{detection.timestamp.strftime('%Y%m%d_%H%M%S')}.{self.config.audio_format}"
            output_filepath = extracted_dir / output_filename

            try:
                subprocess.run(
                    [
                        "sox",
                        str(input_audio_path),
                        str(output_filepath),
                        "trim",
                        str(start_time_seconds),
                        str(extraction_length),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print(f"Extracted {detection.species} to {output_filepath}")
                self.detection_manager.update_detection_extracted_status(detection.id, True)
            except subprocess.CalledProcessError as e:
                import sys
                sys.stderr.write(f"Error extracting audio for {detection.species}: {e.stderr}\n")
            except FileNotFoundError:
                import sys
                sys.stderr.write("Error: sox command not found. Please ensure it's installed and in your PATH.\n")