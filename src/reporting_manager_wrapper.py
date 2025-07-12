import argparse
import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.reporting_manager import ReportingManager
from services.database_manager import DatabaseManager
from utils.config_file_parser import ConfigFileParser

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reporting Manager Wrapper")
    parser.add_argument(
        "action", type=str, help="Action to perform (e.g., most_recent, spectrogram)"
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Number of recent detections to retrieve"
    )
    parser.add_argument(
        "--audio_file",
        type=str,
        help="Path to the audio file for spectrogram generation",
    )
    parser.add_argument(
        "--output_image", type=str, help="Path to save the generated spectrogram image"
    )

    args = parser.parse_args()

    config = ConfigFileParser("etc/birdnet.conf").parse()
    db_manager = DatabaseManager(config.database.path)

    reporting_manager = ReportingManager(db_manager)

    if args.action == "most_recent":
        recent_detections = reporting_manager.get_most_recent_detections(args.limit)
        for detection in recent_detections:
            print(detection)
    elif args.action == "spectrogram":
        if args.audio_file is None or args.output_image is None:
            parser.error(
                "--audio_file and --output_image are required for spectrogram action."
            )
        reporting_manager.generate_spectrogram(args.audio_file, args.output_image)
    else:
        parser.error(f"Unknown action: {args.action}")
