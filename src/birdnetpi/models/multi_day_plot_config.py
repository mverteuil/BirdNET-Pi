from dataclasses import dataclass


@dataclass
class MultiDayPlotConfig:
    """Configuration for multi-day plot data preparation."""

    resample_sel: str
    specie: str
    top_n: int
