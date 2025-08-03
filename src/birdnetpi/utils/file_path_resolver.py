import datetime
import os
from pathlib import Path


class FilePathResolver:
    """Central authority for all file path resolution in BirdNET-Pi.

    Uses environment variables for configuration with sensible defaults.
    Supports both SBC and Docker deployments with unified filesystem layout.
    """

    def __init__(self) -> None:
        """Initialize FilePathResolver with environment-based configuration."""
        # Core directory paths from environment variables
        self.app_dir = Path(os.getenv("BIRDNETPI_APP", "/opt/birdnetpi"))
        self.data_dir = Path(os.getenv("BIRDNETPI_DATA", "/var/lib/birdnetpi"))

        # Legacy base_dir for compatibility during transition
        self.base_dir = str(self.app_dir)

    def get_birdnetpi_config_path(self) -> str:
        """Get the path to the main configuration file.

        Checks BIRDNETPI_CONFIG environment variable first, then falls back to default.
        """
        config_path = os.getenv("BIRDNETPI_CONFIG")
        if config_path:
            return config_path

        # Default: runtime config in data directory
        return str(self.data_dir / "config" / "birdnetpi.yaml")

    def get_config_template_path(self) -> str:
        """Get the path to the configuration template."""
        return str(self.app_dir / "config_templates" / "birdnetpi.yaml")

    def get_models_dir(self) -> str:
        """Get the directory containing BirdNET tensor models."""
        return str(self.data_dir / "models")

    def get_model_path(self, model_filename: str) -> str:
        """Get the full path to a specific model file."""
        # Add .tflite extension if not present
        if not model_filename.endswith(".tflite"):
            model_filename = f"{model_filename}.tflite"
        return str(self.data_dir / "models" / model_filename)

    def get_recordings_dir(self) -> str:
        """Get the directory for audio recordings."""
        return str(self.data_dir / "recordings")

    def get_detection_audio_path(self, species: str, timestamp: datetime.datetime | float) -> str:
        """Get the relative path for saving detection audio files.

        Args:
            species: The detected bird species name
            timestamp: Timestamp of the detection

        Returns:
            Relative path for the detection audio file
        """
        import datetime

        # Convert timestamp to datetime if it's not already
        if isinstance(timestamp, datetime.datetime):
            dt = timestamp
        else:
            dt = datetime.datetime.fromtimestamp(timestamp)

        # Create a safe filename from species name
        safe_species = species.replace(" ", "_").replace("/", "_").replace("'", "")

        # Generate filename with timestamp: species_YYYYMMDD_HHMMSS.wav
        filename = f"{safe_species}_{dt.strftime('%Y%m%d_%H%M%S')}.wav"

        # Return relative path within recordings directory
        return f"detections/{dt.strftime('%Y/%m/%d')}/{filename}"

    def get_database_dir(self) -> str:
        """Get the directory for database files."""
        return str(self.data_dir / "database")

    def get_database_path(self) -> str:
        """Get the path to the main SQLite database."""
        return str(self.data_dir / "database" / "birdnetpi.db")

    def get_ioc_database_path(self) -> str:
        """Get the path to the IOC reference database."""
        return str(self.data_dir / "database" / "ioc_reference.db")

    def get_log_dir(self) -> str:
        """Get the directory for log files (default fallback)."""
        return "/var/log/birdnetpi"

    def get_log_file_path(self, config_log_path: str | None = None) -> str:
        """Get the path to the main log file.

        Args:
            config_log_path: Optional log file path from configuration
        """
        if config_log_path:
            return str(Path(config_log_path).expanduser())
        return "/var/log/birdnetpi/birdnetpi.log"

    def get_temp_dir(self) -> str:
        """Get the temporary directory for cache files."""
        return "/tmp/birdnetpi"

    # Web application paths (in app directory)
    def get_static_dir(self) -> str:
        """Get the directory for static web assets."""
        return str(self.app_dir / "src" / "birdnetpi" / "web" / "static")

    def get_templates_dir(self) -> str:
        """Get the directory for HTML templates."""
        return str(self.app_dir / "src" / "birdnetpi" / "web" / "templates")

    def get_fifo_base_path(self) -> str:
        """Get the base path for FIFO files (temporary)."""
        return self.get_temp_dir()
