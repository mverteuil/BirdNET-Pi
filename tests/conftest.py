from pathlib import Path

import pytest

from src.utils.file_path_resolver import FilePathResolver


@pytest.fixture
def file_path_resolver(tmp_path: Path) -> FilePathResolver:
    """
    Creates a FilePathResolver pointing to a temporary directory
    with mock config files read from the actual templates.
    """
    # Create a realistic runtime config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Read content from actual template files
    birdnet_pi_config_template = Path(
        "config_templates/birdnet_pi_config.yaml.template"
    ).read_text()
    birdnet_conf_template = Path("config_templates/birdnet.conf.template").read_text()

    # Write content to runtime-named files in the temp config dir
    (config_dir / "birdnet_pi_config.yaml").write_text(birdnet_pi_config_template)
    (config_dir / "birdnet.conf").write_text(birdnet_conf_template)

    return FilePathResolver(base_dir=str(tmp_path))
