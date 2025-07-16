from dataclasses import dataclass


@dataclass
class CaddyConfig:
    """Configuration for Caddy web server settings."""

    birdnetpi_url: str
    extracted_path: str
    caddy_pwd: str | None = None
