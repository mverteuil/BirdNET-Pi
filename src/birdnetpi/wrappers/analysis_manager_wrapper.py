import argparse
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from birdnetpi.models.database_models import Base

from birdnetpi.managers.analysis_manager import AnalysisManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.database_service import DatabaseService
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main_cli(analysis_client_service: AnalysisClientService = AnalysisClientService(), detection_event_publisher: DetectionEventPublisher = DetectionEventPublisher()) -> None:
    """Provide the main entry point for the Analysis Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Analysis Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., process_recordings, extract_new_birdsounds)",
    )

    args = parser.parse_args()

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(file_path_resolver.get_birdnet_conf_path()).load_config()

    db_path = config.database.path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_service = DatabaseService(SessionLocal)

    detection_manager = DetectionManager(db_service)
    file_manager = FileManager(config.data.recordings_dir)

    analysis_manager = AnalysisManager(
        config, file_manager, detection_manager, analysis_client_service, detection_event_publisher
    )

    if args.action == "process_recordings":
        analysis_manager.process_recordings()
    elif args.action == "extract_new_birdsounds":
        analysis_manager.extract_new_birdsounds()
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()