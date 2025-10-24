import datetime
import os
from pathlib import Path


class PathResolver:
    """Central authority for all file path resolution in BirdNET-Pi.

    Uses environment variables for configuration with sensible defaults.
    Supports both SBC and Docker deployments with unified filesystem layout.
    """

    def __init__(self) -> None:
        """Initialize PathResolver with environment-based configuration."""
        # Core directory paths from environment variables
        self.app_dir = Path(os.getenv("BIRDNETPI_APP", "/opt/birdnetpi"))
        self.data_dir = Path(os.getenv("BIRDNETPI_DATA", "/var/lib/birdnetpi"))

    def get_birdnetpi_config_path(self) -> Path:
        """Get the path to the main configuration file.

        Checks BIRDNETPI_CONFIG environment variable first, then falls back to default.
        """
        config_path = os.getenv("BIRDNETPI_CONFIG")
        if config_path:
            return Path(config_path)

        # Default: runtime config in data directory
        config_path = self.data_dir / "config" / "birdnetpi.yaml"
        return config_path

    def get_config_template_path(self) -> Path:
        """Get the path to the configuration template."""
        template_path = self.app_dir / "config_templates" / "birdnetpi.yaml"
        return template_path

    def get_template_file_path(self, template_name: str) -> Path:
        """Get the path to a template file in config_templates directory.

        Args:
            template_name: Name of the template file
                (e.g., 'Caddyfile.j2', 'pulseaudio_default.pa.j2')

        Returns:
            Path to the template file
        """
        return self.app_dir / "config_templates" / template_name

    def get_repo_path(self) -> Path:
        """Get the path to the BirdNET-Pi repository root."""
        # The repository root is the app_dir
        return self.app_dir

    def get_data_dir(self) -> Path:
        """Get the data directory path.

        Returns:
            Path to the data directory where all runtime data is stored.
        """
        return self.data_dir

    def get_models_dir(self) -> Path:
        """Get the directory containing BirdNET tensor models."""
        models_dir = self.data_dir / "models"
        return models_dir

    def get_model_path(self, model_filename: str) -> Path:
        """Get the full path to a specific model file."""
        # Add .tflite extension if not present
        if not model_filename.endswith(".tflite"):
            model_filename = f"{model_filename}.tflite"
        model_path = self.data_dir / "models" / model_filename
        return model_path

    def get_recordings_dir(self) -> Path:
        """Get the directory for audio recordings."""
        recordings_dir = self.data_dir / "recordings"
        return recordings_dir

    def get_detection_audio_path(self, scientific_name: str, timestamp: datetime.datetime) -> Path:
        """Get the relative path for saving detection audio files.

        Args:
            scientific_name: The detected bird's scientific name
            timestamp: Timestamp of the detection (datetime object)

        Returns:
            Path relative to recordings_dir for the detection audio file
        """
        # Create a safe filename from scientific name
        safe_name = scientific_name.replace(" ", "_")

        # Generate filename with timestamp including microseconds for uniqueness
        filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{timestamp.microsecond:06d}.wav"

        # Return relative path from recordings_dir: safe_name/filename
        return Path(safe_name) / filename

    def get_database_dir(self) -> Path:
        """Get the directory for database files."""
        database_dir = self.data_dir / "database"
        return database_dir

    def get_database_path(self) -> Path:
        """Get the path to the main SQLite database."""
        database_path = self.data_dir / "database" / "birdnetpi.db"
        return database_path

    def get_ioc_database_path(self) -> Path:
        """Get the path to the IOC reference database."""
        ioc_db_path = self.data_dir / "database" / "ioc_reference.db"
        return ioc_db_path

    def get_wikidata_database_path(self) -> Path:
        """Get the path to the Wikidata reference database.

        Contains multilingual names, image URLs, and conservation status data.
        """
        wikidata_db_path = self.data_dir / "database" / "wikidata_reference.db"
        return wikidata_db_path

    def get_temp_dir(self) -> Path:
        """Get the temporary directory for cache files."""
        return Path("/tmp/birdnetpi")

    # Web application paths (in app directory)
    def get_static_dir(self) -> Path:
        """Get the directory for static web assets."""
        static_dir = self.app_dir / "src" / "birdnetpi" / "web" / "static"
        return static_dir

    def get_templates_dir(self) -> Path:
        """Get the directory for HTML templates."""
        templates_dir = self.app_dir / "src" / "birdnetpi" / "web" / "templates"
        return templates_dir

    def get_locales_dir(self) -> Path:
        """Get the directory for i18n locale files (.po/.mo)."""
        locales_dir = self.app_dir / "locales"
        return locales_dir

    def get_babel_config_path(self) -> Path:
        """Get the path to the Babel configuration file."""
        babel_config_path = self.app_dir / "babel.cfg"
        return babel_config_path

    def get_messages_pot_path(self) -> Path:
        """Get the path to the messages.pot template file."""
        messages_pot_path = self.app_dir / "locales" / "messages.pot"
        return messages_pot_path

    def get_src_dir(self) -> Path:
        """Get the source code directory."""
        src_dir = self.app_dir / "src"
        return src_dir

    def get_fifo_base_path(self) -> Path:
        """Get the base path for FIFO files (temporary)."""
        return self.get_temp_dir()

    def get_update_state_path(self) -> Path:
        """Get the path to the update state file."""
        return self.data_dir / "update_state.json"

    def get_update_lock_path(self) -> Path:
        """Get the path to the update lock file."""
        return self.data_dir / "update.lock"

    def get_rollback_dir(self) -> Path:
        """Get the directory for rollback points."""
        rollback_dir = self.data_dir / "rollback"
        rollback_dir.mkdir(parents=True, exist_ok=True)
        return rollback_dir

    def get_display_simulator_dir(self) -> Path:
        """Get the directory for e-paper display simulator output files.

        Returns:
            Path to the display simulator directory where PNG files are saved.
        """
        return self.data_dir / "display-simulator"
