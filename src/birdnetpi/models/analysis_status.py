from enum import Enum


class AnalysisStatus(Enum):
    """Represents the status of an audio analysis process."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
