import argparse

from .managers.audio_manager import AudioManager
from .utils.config_file_parser import ConfigFileParser
from .utils.file_path_resolver import FilePathResolver

if __name__ == "__main__":
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

    # This is a placeholder for where the config would be loaded
    # In a real application, this would be handled by a config loader
    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(file_path_resolver.get_birdnet_conf_path()).parse()

    audio_manager = AudioManager(config)

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
