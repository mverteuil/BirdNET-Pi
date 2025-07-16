from dataclasses import dataclass


@dataclass
class GitUpdateConfig:
    """Configuration for Git repository updates."""

    remote: str = "origin"
    branch: str = "main"
