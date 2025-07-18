from datetime import datetime  # Import datetime for timestamp conversion

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection  # Import Detection model
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager


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
        # This will involve logic to identify new birdsounds from analysis results
        # and potentially move/copy them using FileManager.
        pass
