import argparse

from birdnetpi.managers.audio_manager import AudioManager
from birdnetpi.services.file_manager import FileManager
from birdnetpi.utils.config_file_parser import ConfigFileParser
from birdnetpi.utils.file_path_resolver import FilePathResolver


def main_cli() -> None:
    """Provide the main entry point for the Audio Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Audio Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., record, custom_record, livestream)",
    )
    parser.add_argument(
        "--duration", type=int, help="Duration for custom recording in seconds"
    )
    parser.add_argument(
        "--output_file", type=str, help="Output file path for custom recording"
    )
    parser.add_argument("--output_url", type=str, help="Output URL for livestreaming")

    args = parser.parse_args()

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(
        file_path_resolver.get_birdnet_pi_config_path()
    ).load_config()
    file_manager = FileManager(file_path_resolver.repo_root)

    audio_manager = AudioManager(file_manager, config)

    if args.action == "record":
        audio_manager.record()
    elif args.action == "custom_record":
        if args.duration is None or args.output_file is None:
            parser.error(
                "--duration and --output_file are required for custom_record action."
            )
        audio_manager.custom_record(args.duration, args.output_file)
    elif args.action == "livestream":
        if args.output_url is None:
            parser.error("--output_url is required for livestream action.")
        audio_manager.livestream(args.output_url)
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
