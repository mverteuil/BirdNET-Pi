import argparse

from .services.notification_service import NotificationService
from .utils.config_file_parser import ConfigFileParser

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notification Service Wrapper")
    parser.add_argument(
        "action", type=str, help="Action to perform (e.g., species_notifier)"
    )
    parser.add_argument("--species_name", type=str, help="Name of the species detected")
    parser.add_argument("--confidence", type=float, help="Confidence of the detection")

    args = parser.parse_args()

    config = ConfigFileParser("etc/birdnet.conf").parse()
    notification_service = NotificationService(config)

    if args.action == "species_notifier":
        if args.species_name is None or args.confidence is None:
            parser.error(
                "--species_name and --confidence are required for species_notifier action."
            )
        notification_service.species_notifier(args.species_name, args.confidence)
    else:
        parser.error(f"Unknown action: {args.action}")
