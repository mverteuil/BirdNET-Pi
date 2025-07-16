import argparse
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from birdnetpi.models.database_models import Base
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.managers.reporting_manager import ReportingManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main_cli() -> None:
    """Provide the main entry point for the Reporting Manager Wrapper CLI."""
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

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(
        file_path_resolver.get_birdnet_pi_config_path()
    ).load_config()

    db_path = config.database.path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_service = DatabaseService(SessionLocal)

    detection_manager = DetectionManager(db_service)

    reporting_manager = ReportingManager(detection_manager, file_path_resolver, ConfigFileParser(file_path_resolver.get_birdnet_pi_config_path()))

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


if __name__ == "__main__":
    main_cli()