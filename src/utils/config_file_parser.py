import yaml
from BirdNET_Pi.src.models.birdnet_config import BirdNETConfig


class ConfigFileParser:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def load_config(self) -> BirdNETConfig:
        with open(self.config_path, "r") as f:
            config_data = yaml.safe_load(f)
        # Placeholder for actual mapping to BirdNETConfig dataclass
        return BirdNETConfig(**config_data)
