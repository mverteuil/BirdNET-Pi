from dataclasses import dataclass


@dataclass
class ClientArgs:
    """Represents arguments passed to client-side scripts."""

    # Arguments for client-side scripts, e.g., analysis, recording
    input_path: str = ""
    output_path: str = ""
    duration: int = 0
    # Add other common arguments as needed
