import argparse

from birdnetpi.managers.data_manager import DataManager
from birdnetpi.managers.database_manager import DatabaseManager
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main_cli() -> None:
    """Provide the main entry point for the Data Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Data Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., cleanup, clear_all_data)",
    )

    args = parser.parse_args()

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(
        file_path_resolver.get_birdnet_pi_config_path()
    ).load_config()

    file_manager = FileManager(config.data.recordings_dir)
    database_manager = DatabaseManager(config.database.path)
    database_manager.initialize_database()

    data_manager = DataManager(config, file_manager, database_manager)

    if args.action == "cleanup":
        data_manager.cleanup()
    elif args.action == "clear_all_data":
        data_manager.clear_all_data()
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
