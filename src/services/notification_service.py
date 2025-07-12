from models.birdnet_config import BirdNETConfig


class NotificationService:
    def __init__(self, config: BirdNETConfig):
        self.config = config

    def species_notifier(self, species_name: str, confidence: float):
        # Placeholder for actual notification logic
        # This would involve checking config.apprise_input, etc.
        print(
            f"Notification: New species detected - {species_name} with confidence {confidence:.2f}"
        )

        if self.config.apprise_notify_each_detection:
            print(f"Sending Apprise notification for {species_name}")
            # Actual Apprise call would go here

        # More complex logic for new species, weekly reports, etc. would be added here
