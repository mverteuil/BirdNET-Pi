import logging
import subprocess

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.services.file_manager import FileManager

log = logging.getLogger(__name__)


class AudioExtractionService:
    """Handles the extraction of specific audio segments (birdsounds) from recordings."""

    def __init__(
        self,
        config: BirdNETConfig,
        file_manager: FileManager,
        detection_manager: DetectionManager,
    ) -> None:
        self.config = config
        self.file_manager = file_manager
        self.detection_manager = detection_manager

    def extract_birdsounds_for_detection(self, detection_id: int) -> None:
        """Extract an audio segment for a given detection ID."""
        detection = self.detection_manager.get_detection_by_id(detection_id)
        if not detection:
            log.warning(
                "AudioExtractionService: "
                f"Detection with ID {detection_id} not found. Skipping extraction."
            )
            return

        input_audio_path = self.file_manager.get_full_path(detection.audio_file_path)
        audio_file = self.detection_manager.get_audio_file_by_path(detection.audio_file_path)

        if not audio_file:
            log.error(
                "AudioExtractionService: "
                f"AudioFile record not found for {detection.audio_file_path}. "
                "Skipping extraction."
            )
            return

        extracted_dir = self.file_manager.get_full_path(self.config.data.extracted_dir)
        extracted_dir.mkdir(parents=True, exist_ok=True)

        extraction_length = (
            float(self.config.extraction_length) if self.config.extraction_length else 6.0
        )

        # Calculate the start time for sox trim based on recording_start_time
        time_difference = detection.timestamp - audio_file.recording_start_time
        start_time_seconds = time_difference.total_seconds()

        output_filename = (
            f"{detection.species.replace(' ', '_')}_"
            f"{detection.timestamp.strftime('%Y%m%d_%H%M%S')}."
            f"{self.config.audio_format}"
        )
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
            log.info(f"AudioExtractionService: Extracted {detection.species} to {output_filepath}")
            self.detection_manager.update_detection_extracted_status(detection.id, True)
        except subprocess.CalledProcessError as e:
            log.error(
                "AudioExtractionService: "
                f"Error extracting audio for {detection.species}: {e.stderr}"
            )
        except FileNotFoundError:
            log.error(
                "AudioExtractionService: Error: sox command not found. "
                "Please ensure it's installed and in your PATH."
            )

    def extract_all_unextracted_birdsounds(self) -> None:
        """Extract all birdsounds that have not yet been extracted."""
        log.info("AudioExtractionService: Extracting all unextracted birdsounds...")
        unextracted_detections = self.detection_manager.get_all_detections(extracted=False)
        for detection in unextracted_detections:
            self.extract_birdsounds_for_detection(detection.id)
