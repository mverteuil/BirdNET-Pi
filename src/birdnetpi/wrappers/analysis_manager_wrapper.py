import argparse

from birdnetpi.managers.analysis_manager import AnalysisManager
from birdnetpi.managers.database_manager import DatabaseManager
from birdnetpi.services.detection_event_publisher import DetectionEventPublisher
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main_cli() -> None:
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

    db_manager = DatabaseManager(config.database.path)
    file_manager = FileManager(config.data.recordings_dir)

    analysis_manager = AnalysisManager(
        config, db_manager, file_manager, file_path_resolver, DetectionEventPublisher()
    )

    if args.action == "process_recordings":
        analysis_manager.process_recordings()
    elif args.action == "extract_new_birdsounds":
        analysis_manager.extract_new_birdsounds()
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
