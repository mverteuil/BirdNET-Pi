import argparse

from birdnetpi.managers.analysis_manager import AnalysisManager
from birdnetpi.managers.detection_manager import DetectionManager
from birdnetpi.services.analysis_client_service import AnalysisClientService
from birdnetpi.services.audio_extraction_service import AudioExtractionService
from birdnetpi.services.audio_processor_service import AudioProcessorService
from birdnetpi.services.database_service import DatabaseService
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
    # Add argument for audio file path if action is process_recordings
    parser.add_argument(
        "--audio_file_path",
        type=str,
        help="Path to the audio file to process (required for process_recordings action)",
        default=None,
    )

    args = parser.parse_args()

    file_path_resolver = FilePathResolver()
    config = ConfigFileParser(
        file_path_resolver.get_birdnet_pi_config_path()
    ).load_config()

    db_service = DatabaseService(config.data.db_path)

    detection_manager = DetectionManager(db_service)
    file_manager = FileManager(file_path_resolver.base_dir)

    # Instantiate services with config
    analysis_client_service = AnalysisClientService(config)
    audio_processor_service = AudioProcessorService()
    audio_extraction_service = AudioExtractionService(
        config, file_manager, detection_manager
    )
    detection_event_publisher = DetectionEventPublisher()

    analysis_manager = AnalysisManager(
        config,
        file_manager,
        detection_manager,
        analysis_client_service,
        audio_processor_service,
        audio_extraction_service,
        detection_event_publisher,
    )

    if args.action == "process_recordings":
        if not args.audio_file_path:
            parser.error(
                "--audio_file_path is required for 'process_recordings' action."
            )
        analysis_manager.process_audio_for_analysis(args.audio_file_path)
    elif args.action == "extract_new_birdsounds":
        analysis_manager.extract_new_birdsounds()
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
