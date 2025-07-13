import argparse

from .managers.analysis_manager import AnalysisManager
from .services.database_manager import DatabaseManager
from .services.file_manager import FileManager
from .utils.config_file_parser import ConfigFileParser
from .utils.file_path_resolver import FilePathResolver

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analysis Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., process_recordings, extract_new_birdsounds)",
    )

    args = parser.parse_args()

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(file_path_resolver.get_birdnet_conf_path()).parse()

    db_manager = DatabaseManager(config.database.path)
    file_manager = FileManager(config.data.recordings_dir)

    analysis_manager = AnalysisManager(
        config, db_manager, file_manager, file_path_resolver
    )

    if args.action == "process_recordings":
        analysis_manager.process_recordings()
    elif args.action == "extract_new_birdsounds":
        analysis_manager.extract_new_birdsounds()
    else:
        parser.error(f"Unknown action: {args.action}")
