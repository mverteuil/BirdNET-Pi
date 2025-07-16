from dataclasses import dataclass


@dataclass
class DailyPlotConfig:
    """Dataclass to hold configuration for the daily plot."""

    resample_sel: str
    specie: str
