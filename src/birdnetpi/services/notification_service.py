from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.database_models import Detection


class NotificationService:
    """Manages sending notifications based on detection events."""

    def __init__(self, config: BirdNETConfig) -> None:
        self.config = config

    def species_notifier(self, detection: Detection) -> None:
        """Notify about a new species detection."""
        species_name = detection.species
        confidence = detection.confidence

        # Placeholder for actual notification logic
        # This would involve checking config.apprise_input, etc.
        print(
            f"Notification: New species detected - {species_name} with confidence {confidence:.2f}"
        )

        if self.config.apprise_notify_each_detection:
            print(f"Sending Apprise notification for {species_name}")
            # Actual Apprise call would go here

        # More complex logic for new species, weekly reports, etc. would be added here
