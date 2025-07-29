# THIS FILE IS MARKED FOR DEATH
import datetime
import logging
import os

from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.audio_extraction_service import AudioExtractionService
from birdnetpi.services.audio_processor_service import AudioProcessorService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager

log = logging.getLogger(__name__)


class AnalysisManager:
    """Manages the analysis of audio files, storing results, and publishing detection events."""

    def __init__(
        self,
        config: BirdNETConfig,
        file_manager: FileManager,
        detection_manager: DetectionManager,
        analysis_client_service: AnalysisClientService,
        audio_processor_service: AudioProcessorService,
        audio_extraction_service: AudioExtractionService,
        detection_event_publisher: DetectionEventPublisher,
    ) -> None:
        self.config = config
        self.file_manager = file_manager
        self.detection_manager = detection_manager
        self.analysis_client_service = analysis_client_service
        self.audio_processor_service = audio_processor_service
        self.audio_extraction_service = audio_extraction_service
        self.detection_event_publisher = detection_event_publisher

        self.include_list = []
        self.exclude_list = []
        self.whitelist_list = []

    def _load_custom_species_list(self, path: str) -> list[str]:
        slist = []
        if os.path.isfile(path):
            with open(path) as csfile:
                for line in csfile.readlines():
                    slist.append(line.replace("\r", "").replace("\n", ""))
        return slist

    def _is_human_detection(self, raw_predictions: list[tuple[str, float]]) -> bool:
        for p_entry in raw_predictions:
            if "Human" in p_entry[0]:
                return True
        return False

    def _filter_predictions(
        self,
        raw_predictions: list[tuple[str, float]],
        predicted_species_list: list[str],
    ) -> list[tuple[str, float]]:
        confident_predictions = []
        for entry in raw_predictions:
            if entry[1] >= self.config.confidence:
                if entry[0] not in self.include_list and len(self.include_list) != 0:
                    log.warning(
                        "AnalysisManager: Excluded as INCLUDE_LIST is active but this "
                        "species is not in it: %s",
                        entry[0],
                    )
                elif entry[0] in self.exclude_list and len(self.exclude_list) != 0:
                    log.warning(
                        "AnalysisManager: Excluded as species in EXCLUDE_LIST: %s",
                        entry[0],
                    )
                elif (
                    entry[0] not in predicted_species_list
                    and len(predicted_species_list) != 0
                    and entry[0] not in self.whitelist_list
                ):
                    log.warning(
                        "AnalysisManager: Excluded as below Species Occurrence Frequency "
                        "Threshold: %s",
                        entry[0],
                    )
                else:
                    confident_predictions.append(entry)
        return confident_predictions

    def _predictions_to_detections(
        self,
        confident_predictions: list[tuple[str, float]],
        audio_file_path: str,
        pred_start: float,
        pred_end: float,
    ) -> list[dict]:
        detections = []
        for entry in confident_predictions:
            d = {
                "species": entry[0],
                "confidence": entry[1],
                # Placeholder, needs actual timestamp from audio_file_path
                "timestamp": datetime.datetime.now(),
                "audio_file_path": audio_file_path,
                "Com_Name": entry[0],  # Assuming common name is the same as species for now
                "Sci_Name": entry[0],  # Assuming scientific name is the same as species for now
                "Lat": self.config.latitude,
                "Lon": self.config.longitude,
                "Cutoff": self.config.cutoff,
                "Week": self.config.week,
                "Sens": self.config.sensitivity,
                "Overlap": self.config.overlap,
                "start_time_seconds": pred_start,  # Add start time of the chunk
                "end_time_seconds": pred_end,  # Add end time of the chunk
            }
            detections.append(d)
        return detections

    def process_audio_for_analysis(self, audio_file_path: str) -> list[dict]:
        """Process an audio file for analysis, store results, and publish events."""
        log.info(f"AnalysisManager: Processing audio for analysis: {audio_file_path}")

        self.include_list = self._load_custom_species_list(
            os.path.expanduser("~/BirdNET-Pi/include_species_list.txt")
        )
        self.exclude_list = self._load_custom_species_list(
            os.path.expanduser("~/BirdNET-Pi/exclude_species_list.txt")
        )
        self.whitelist_list = self._load_custom_species_list(
            os.path.expanduser("~/BirdNET-Pi/whitelist_species_list.txt")
        )

        try:
            audio_chunks = self.audio_processor_service.read_audio_data(
                audio_file_path, self.config.overlap
            )
        except Exception as e:
            log.error(f"AnalysisManager: Error reading audio data: {e}")
            return []

        all_detections = []
        predicted_species_list = self.analysis_client_service.get_filtered_species_list(
            self.config.latitude, self.config.longitude, self.config.week
        )

        pred_start = 0.0
        for chunk in audio_chunks:
            raw_predictions = self.analysis_client_service.get_raw_prediction(
                chunk,
                self.config.latitude,
                self.config.longitude,
                self.config.week,
                self.config.sensitivity,
            )

            if self._is_human_detection(raw_predictions):
                raw_predictions = [("Human_Human", 0.0)] * len(raw_predictions)

            pred_end = pred_start + 3.0  # Assuming 3-second chunks

            confident_predictions = self._filter_predictions(
                raw_predictions, predicted_species_list
            )
            detections = self._predictions_to_detections(
                confident_predictions, audio_file_path, pred_start, pred_end
            )
            all_detections.extend(detections)

            pred_start = pred_end - self.config.overlap

        # Store in database and publish events
        if all_detections:
            for result_dict in all_detections:
                detection = Detection(
                    species=result_dict["species"],
                    confidence=result_dict["confidence"],
                    timestamp=result_dict["timestamp"],
                    audio_file_path=result_dict["audio_file_path"],
                )
                new_detection = self.detection_manager.add_detection(detection)
                log.info(f"AnalysisManager: Added detection to DB: {new_detection.species}")

                self.detection_event_publisher.publish_detection(new_detection)

        return all_detections

    def extract_new_birdsounds(self) -> None:
        """Extract new birdsounds by delegating to the AudioExtractionService."""
        self.audio_extraction_service.extract_all_unextracted_birdsounds()
