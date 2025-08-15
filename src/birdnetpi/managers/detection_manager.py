"""Detection event handling and notification manager.

This manager is responsible for emitting detection events to various
subscribers (websockets, MQTT, webhooks, etc.) when new detections occur.
All data access operations have been moved to DataManager.
"""

from sqlalchemy.exc import SQLAlchemyError

from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.utils.signals import detection_signal
from birdnetpi.web.models.detection import DetectionEvent


class DetectionManager:
    """Manages detection event emission and notifications.

    This class is now focused solely on event handling. All data access
    operations have been moved to DataManager for a single source of truth.
    """

    def __init__(
        self,
        bnp_database_service: DatabaseService,
    ) -> None:
        self.bnp_database_service = bnp_database_service

    def emit_detection_event(self, detection: Detection) -> None:
        """Emit a detection event to all subscribers via Blinker signal.

        This method is called after a detection has been saved to the database
        by DataManager. It notifies all subscribers (websockets, MQTT, webhooks)
        about the new detection.

        Args:
            detection: The Detection model instance that was created
        """
        # Emit Blinker signal for subscribers
        detection_signal.send(self, detection=detection)

    def create_detection(self, detection_event: DetectionEvent) -> Detection:
        """Legacy method kept for backward compatibility.

        This method now creates the detection and emits the event.
        Data persistence is handled by DataManager in the router.
        """
        with self.bnp_database_service.get_db() as db:
            try:
                # Create AudioFile record
                audio_file = AudioFile(
                    file_path=detection_event.audio_file_path,
                    duration=detection_event.duration,
                    size_bytes=detection_event.size_bytes,
                )
                db.add(audio_file)
                db.flush()  # Flush to get audio_file.id before committing

                # Create Detection record
                detection = Detection(
                    species_tensor=detection_event.species_tensor,
                    scientific_name=detection_event.scientific_name,
                    common_name=detection_event.common_name,
                    confidence=detection_event.confidence,
                    timestamp=detection_event.timestamp,
                    audio_file_id=audio_file.id,
                    latitude=detection_event.latitude,
                    longitude=detection_event.longitude,
                    species_confidence_threshold=detection_event.species_confidence_threshold,
                    week=detection_event.week,
                    sensitivity_setting=detection_event.sensitivity_setting,
                    overlap=detection_event.overlap,
                )
                db.add(detection)
                db.commit()
                db.refresh(detection)

                # Emit Blinker signal
                self.emit_detection_event(detection)

                return detection
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error creating detection: {e}")
                raise
